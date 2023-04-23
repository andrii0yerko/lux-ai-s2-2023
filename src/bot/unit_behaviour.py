import itertools
import logging
from collections import Counter
from typing import NamedTuple

import numpy as np

from bot.logging import BehaviourLoggingAdapter
from bot.task_manager import TaskManager
from bot.map_manager import MapManager
from lux.kit import GameState
from lux.unit import Unit, move_deltas
from lux.utils import direction_to


class FoundPath(NamedTuple):
    target: np.ndarray
    directions: list
    avoid_collisions: bool = False

    @property
    def direction(self):
        return self.directions[0]


class UnitBehaviour:
    # __registry = {}

    # def __new__(cls, unit: Unit, *args, **kwargs):
    #     if unit.unit_id not in cls.__registry:
    #         cls.__registry[unit.unit_id] = super(UnitBehaviour, cls).__new__(cls)
    #     return cls.__registry[unit.unit_id]

    def __init__(self, unit: Unit, game_state: GameState, manager: TaskManager, map_state: MapManager):
        self.unit = unit
        self.unit_id = self.unit.unit_id

        self.game_state = game_state
        self.manager = manager
        self.map_state = map_state

        self.closest_factory_tile = self.manager.register_bot(self.unit_id, unit)
        factory_id = self.manager.bot_factory[self.unit_id]
        self.factory = self.map_state.factories[factory_id]

        self.target = self.manager.bot_targets.get(self.unit_id)

        logger = logging.getLogger(__class__.__name__)

        # Create adapter with custom prefix
        self.logger = BehaviourLoggingAdapter(logger, {"behaviour": self})

        unit_cfg = self.game_state.env_cfg.ROBOTS[unit.unit_type]
        self.battery_capacity = unit_cfg.BATTERY_CAPACITY
        self.cargo_space = unit_cfg.CARGO_SPACE
        self.def_move_cost = unit_cfg.MOVE_COST
        self.rubble_dig_cost = unit_cfg.DIG_COST

        self.actions = []

    def get_direction(self, unit, sorted_tiles) -> FoundPath:
        closest_tile = np.array(sorted_tiles[0])
        path = FoundPath(closest_tile, self.map_state.shortest_path(unit.pos, closest_tile))
        # direction = direction_to(np.array(unit.pos), closest_tile)
        k = 0
        unit_type = unit.unit_type
        self.logger.debug(f"get_direction: {path.direction}")

        while self.map_state.check_collision(np.array(unit.pos), path.direction, unit_type) and k < min(len(sorted_tiles) - 1, 500):
            k += 1
            alternative_tile = np.array(sorted_tiles[k])
            path = FoundPath(alternative_tile, self.map_state.shortest_path(unit.pos, alternative_tile), True)
            # direction = direction_to(np.array(unit.pos), alternative_tile)
            self.logger.debug(f"get_direction change: {path.direction}")

        if self.map_state.check_collision(unit.pos, path.direction, unit_type):
            for direction_x in np.arange(4, -1, -1):
                if not self.map_state.check_collision(np.array(unit.pos), direction_x, unit_type):
                    path = FoundPath(closest_tile, [direction_x], True)
                    self.logger.debug(f"get_direction change search: {direction_x}")
                    break

        # TODO why this is even possible? Previous block should avoid any collisions by choosing direction 0
        if self.map_state.check_collision(np.array(unit.pos), path.direction, unit_type):
            direction = np.random.choice(np.arange(5))
            path = FoundPath(closest_tile, [direction], True)
            self.logger.debug(f"get_direction change finally: {path.direction}")

        self.logger.info(f"{unit.pos}, {closest_tile}, directions, {path.directions}")

        return path

    def _move_to(self, sorted_alternatives):
        # self.logger.debug("move to %s -> %s", self.unit.pos, sorted_alternatives)
        unit = self.unit
        game_state = self.game_state

        path = self.get_direction(unit, sorted_alternatives)
        move_cost = unit.move_cost(game_state, path.direction)
        # check move_cost is not None, meaning that direction is not blocked
        # check if unit has enough power to move and update the action queue.
        if move_cost is not None:  # and unit.power >= move_cost + unit.action_queue_cost(game_state):
            self.actions += [unit.move(d, repeat=False, n=len(list(gr))) for d, gr in itertools.groupby(path.directions)]
            self.manager.bot_targets[self.unit_id] = path.target
            self.logger.info(f"new movement queue {path.directions} {self.actions}")

    def _return_to_factory(self):
        """
        transfer resources and take power if unit in factory
        if not - move to it

        # TODO: action sequences. Transfer ore or ice first depending on task and/or quantity
        """
        unit = self.unit
        if not self.adjacent_to_factory:
            self.task.action = "return"
            self.logger.info("move to factory")
            self._move_to([self.closest_factory_tile])
            if unit.unit_id in self.manager.bot_targets:
                self.manager.bot_targets.pop(unit.unit_id)

        self.task.action = "continue"
        if unit.cargo.ice > 0:
            self.actions += [unit.transfer(0, 0, unit.cargo.ice, repeat=False)]
            self.logger.info("transfer ice")
        elif unit.cargo.ore > 0:
            self.actions += [unit.transfer(0, 1, unit.cargo.ore, repeat=False)]
            self.logger.info("transfer ore")
        elif unit.power < self.battery_capacity * 0.1:
            self.actions += [unit.pickup(4, self.battery_capacity - unit.power)]
            self.logger.info("pickup power")

    def _task_ice(self):
        unit = self.unit
        game_state = self.game_state

        if (
            unit.cargo.ice < self.cargo_space
            and unit.power > unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.def_move_cost * self.distance_to_factory
            and not (self.factory.cargo.water <= (10 if self.game_state.is_day() else 20) and unit.cargo.ice)
            # and self.task.action != "return"
        ):
            # compute the distance to each ice tile from this unit and pick the closest

            sorted_ice = self.map_state.get_tiles_distances(unit.pos, "ice")[0]
            # if we have reached the ice tile, start mining if possible
            if not (sorted_ice == unit.pos).all(1).any():
                self.logger.info("move to ice")
                self._move_to(sorted_ice)
                # if unit.power >= unit.dig_cost(game_state) + unit.action_queue_cost(game_state):
            self.actions += [unit.dig(repeat=True)]
            self.logger.info("reached ice, dig")

        elif (
            unit.cargo.ice >= self.cargo_space
            or unit.power <= unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.def_move_cost * self.distance_to_factory
        ):
            self._return_to_factory()

    def _task_ore(self):
        unit = self.unit
        game_state = self.game_state
        if (
            unit.cargo.ore < self.cargo_space
            and unit.power > unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.def_move_cost * self.distance_to_factory
            # and self.task.action != "return"
        ):
            # compute the distance to each ore tile from this unit and pick the closest
            sorted_ore = self.map_state.get_tiles_distances(unit.pos, "ore")[0]
            # if we have reached the ore tile, start mining if possible
            if not (sorted_ore == unit.pos).all(1).any():
                self.logger.info("move to ore")
                self._move_to(sorted_ore)
                # if unit.power >= unit.dig_cost(game_state) + unit.action_queue_cost(game_state):
            self.actions += [unit.dig(repeat=True)]
            self.logger.info("ore reached, dig")

        elif (
            unit.cargo.ore >= self.cargo_space
            or unit.power <= unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.def_move_cost * self.distance_to_factory
        ):
            self._return_to_factory()

    def _task_attack_lichen(self):
        unit = self.unit
        game_state = self.game_state
        if unit.power > unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.rubble_dig_cost:
            sorted_ore = self.map_state.get_tiles_distances(unit.pos, "opponent_lichen")[0]
            if not (sorted_ore == unit.pos).all(1).any():
                self.logger.info("move to opponent lichen")
                self._move_to(sorted_ore)
                # if unit.power >= unit.dig_cost(game_state) + unit.action_queue_cost(game_state):
            self.actions += [unit.dig(repeat=True)]
            self.logger.info("opponent lichen reached, dig")

        elif (
            unit.cargo.ore >= self.cargo_space
            or unit.power <= unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.def_move_cost * self.distance_to_factory
        ):
            self._return_to_factory()

    def _task_protect_border(self):
        unit = self.unit
        # game_state = self.game_state
        # if (
        #     unit.cargo.ore < self.cargo_space
        #     and unit.power > unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.def_move_cost * self.distance_to_factory
        #     # and self.task.action != "return"
        # ):
        # compute the distance to each ore tile from this unit and pick the closest
        sorted_tiles = self.map_state.get_tiles_distances(unit.pos, "factory_border")[0]
        # if we have reached the ore tile, start mining if possible
        if not (sorted_tiles == unit.pos).all(1).any():
            self.logger.info("move to border")
            self._move_to(sorted_tiles)
            # if unit.power >= unit.dig_cost(game_state) + unit.action_queue_cost(game_state):
        self.actions += []
        self.logger.info("border reached, wait")

        # elif (
        #     unit.cargo.ore >= self.cargo_space
        #     or unit.power <= unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.def_move_cost * self.distance_to_factory
        # ):
        #     self._return_to_factory()

    def _task_rubble(self):
        unit = self.unit
        game_state = self.game_state

        if (
            unit.power
            > unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.rubble_dig_cost
            # and self.task.action != "return"
        ):
            # compute the distance to each rubble tile from this unit and pick the closest

            sorted_rubble = self.map_state.get_tiles_distances(unit.pos, "rubble")[0]
            if len(sorted_rubble):
                # if we have reached the rubble tile, start mining if possible
                if not (sorted_rubble == unit.pos).all(1).any():
                    self.logger.info("move to rubble")
                    self._move_to(sorted_rubble)
                    # if unit.power >= unit.dig_cost(game_state) + unit.action_queue_cost(game_state):
                self.actions += [unit.dig(repeat=True)]
                self.logger.info("rubble reached, dig")
            else:
                self.logger.info("no tiles to dig")
                self._task_protect_border()

        elif unit.power <= unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.rubble_dig_cost:
            self._return_to_factory()

    def _can_destroy_enemy(self, enemy):
        self.logger.debug("_can_destroy_enemy %s vs %s", self.unit.pos, enemy.pos)
        unit = self.unit

        if unit.unit_type == "LIGHT" and enemy.unit_type == "HEAVY":
            return False
        if unit.unit_type == "HEAVY" and enemy.unit_type == "LIGHT":
            return True

        path = self.map_state.shortest_path(unit.pos, enemy.pos)
        move_cost = self.map_state.shortest_path_cost(unit.pos, enemy.pos)
        move_cost = (move_cost / 20) if unit.unit_type == "LIGHT" else move_cost

        new_queue = self._should_continue_queue([unit.move(path[0])])
        queue_cost = 0 if new_queue else unit.action_queue_cost(self.game_state)
        return unit.power - queue_cost - move_cost > enemy.power

    def _fight(self, pos_min_distance, min_distance):
        closest_enemy = self.map_state.get_robot_by_pos(pos_min_distance)

        if min_distance <= 2:
            if self._can_destroy_enemy(closest_enemy):
                self.logger.info("РЕЗНЯ")
                self._move_to([pos_min_distance])
            elif not self.adjacent_to_factory:
                self.logger.info("step back")
                adjacent_tiles = self.unit.adjacent_tiles()
                dist_enemy = np.sum(np.abs(adjacent_tiles - pos_min_distance), 1)
                dist_factory = np.sum(np.abs(adjacent_tiles - self.closest_factory_tile), 1)
                dist = 2 * dist_enemy - dist_factory

                candidates = adjacent_tiles[np.argsort(dist)][::-1]
                self.logger.info(f"candidates: {candidates}", )
                self._move_to(candidates)
            else:
                self._return_to_factory()
            return True
        return False

    def _enemy_is_near(self):
        unit = self.unit

        opp_pos, opponent_unit_distances = self.map_state.get_tiles_distances(unit.pos, "enemy")

        if len(opp_pos) != 0:
            min_distance = opponent_unit_distances[0]
            pos_min_distance = opp_pos[0]
            self._fight(pos_min_distance, min_distance)

    def _task_kill(self):
        # TODO: attack lichen
        unit = self.unit
        game_state = self.game_state

        opp_pos, opponent_unit_distances = self.map_state.get_tiles_distances(unit.pos, "enemy")

        if len(opp_pos) != 0:
            min_distance = opponent_unit_distances[0]
            pos_min_distance = opp_pos[0]

            if self._fight(pos_min_distance, min_distance):
                pass

            else:
                if unit.power > unit.action_queue_cost(game_state):
                    self.logger.info("move for attack")
                    self._move_to([pos_min_distance])
                else:
                    self._return_to_factory()
        else:
            self._task_rubble()

    def _should_continue_queue(self, actions):
        return (
            len(self.unit.action_queue)
            and len(actions)  # it will be empty, if unit is out of power
            and np.all(self.unit.action_queue[0, :3] == actions[0][:3])
        )

    def _update_botpos(self, queue, is_new=False):
        self.logger.info("_update_botpos %s", queue)
        if queue[0][0] != 0:
            return

        direction = queue[0][1]
        move_cost = self.unit.move_cost(self.game_state, direction)
        if is_new:
            move_cost += self.unit.action_queue_cost(self.game_state)

        if self.unit.power >= move_cost:
            self.map_state.botpos[self.unit.unit_id] = tuple(np.array(self.unit.pos) + move_deltas[direction])

    def act(self):
        # Assigning task for the bot
        actions = {}

        unit_id = self.unit.unit_id
        unit = self.unit

        self.logger.info(f"{self.unit} current action queue: {self.unit.action_queue}, task: {self.manager.bots.get(unit_id)}")

        self.distance_to_factory = np.mean(np.subtract(self.closest_factory_tile, unit.pos) ** 2)
        self.adjacent_to_factory = self.distance_to_factory <= 1

        if unit.power < unit.action_queue_cost(self.game_state):
            self.logger.info("no power, skip")
            return {}

        self.task = self.manager.get_bot_task(unit_id)
        task_method = {
            "ice": self._task_ice,
            "ore": self._task_ore,
            "rubble": self._task_rubble,
            "kill": self._task_kill,
            "defend": self._task_kill,
        }[self.task.task]

        if task_method != self._task_kill:
            self._enemy_is_near()
        task_method()

        if self._should_continue_queue(self.actions):
            self.logger.info("continue queue")
            self._update_botpos(self.unit.action_queue)
            actions = {}

        elif self.actions:
            actions = {unit_id: self.actions[:20]}
            self._update_botpos(self.actions, is_new=True)

        return actions
