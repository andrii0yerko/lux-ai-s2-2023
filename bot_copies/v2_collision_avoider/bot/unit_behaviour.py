import itertools
import logging
from collections import Counter
from typing import NamedTuple

import numpy as np

from bot.logging import BehaviourLoggingAdapter
from bot.state_manager import StateManager
from lux.kit import GameState
from lux.unit import Unit, move_deltas


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

    def __init__(self, unit: Unit, game_state: GameState, manager: StateManager):
        self.unit = unit
        self.unit_id = self.unit.unit_id

        self.game_state = game_state
        self.manager = manager

        self.closest_factory_tile = self.manager.register_bot(self.unit_id, unit)
        factory_id = self.manager.bot_factory[self.unit_id]
        self.factory = self.manager.factories[factory_id]

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

    def assign_to_tile(self, possible_locations):
        unit = self.unit
        num_assigned = Counter(map(tuple, (v for k, v in self.manager.bot_targets.items() if k != unit.unit_id)))

        distances = np.mean((possible_locations - unit.pos) ** 2, 1)
        num_assigned = np.array([num_assigned.get(tuple(pos), 0) for pos in possible_locations])
        # TODO adjust num_assigned depending of distance to _factory_

        idx = np.argsort(distances + 2 * num_assigned)
        self.manager.bot_targets[unit.unit_id] = possible_locations[idx][0]
        return possible_locations[idx]

    def get_direction(self, unit, sorted_tiles) -> FoundPath:
        closest_tile = np.array(sorted_tiles[0])
        path = FoundPath(closest_tile, self.manager.shortest_path(unit.pos, closest_tile))
        # direction = direction_to(np.array(unit.pos), closest_tile)
        k = 0
        unit_type = unit.unit_type
        self.logger.debug(f"get_direction: {path.direction}")

        while self.manager.check_collision(np.array(unit.pos), path.direction, unit_type) and k < min(len(sorted_tiles) - 1, 500):
            k += 1
            alternative_tile = np.array(sorted_tiles[k])
            path = FoundPath(alternative_tile, self.manager.shortest_path(unit.pos, alternative_tile), True)
            # direction = direction_to(np.array(unit.pos), alternative_tile)
            self.logger.debug(f"get_direction change: {path.direction}")

        if self.manager.check_collision(unit.pos, path.direction, unit_type):
            for direction_x in np.arange(4, -1, -1):
                if not self.manager.check_collision(np.array(unit.pos), direction_x, unit_type):
                    path = FoundPath(closest_tile, [direction_x], True)
                    self.logger.debug(f"get_direction change search: {direction_x}")
                    break

        # TODO why this is even possible? Previous block should avoid any collisions by choosing direction 0
        if self.manager.check_collision(np.array(unit.pos), path.direction, unit_type):
            direction = np.random.choice(np.arange(5))
            path = FoundPath(closest_tile, [direction], True)
            self.logger.debug(f"get_direction change finally: {path.direction}")

        self.logger.info(f"{unit.pos}, {closest_tile}, directions, {path.directions}")

        return path

    def _move_to(self, sorted_alternatives):
        unit = self.unit
        game_state = self.game_state

        path = self.get_direction(unit, sorted_alternatives)
        move_cost = unit.move_cost(game_state, path.direction)
        # check move_cost is not None, meaning that direction is not blocked
        # check if unit has enough power to move and update the action queue.
        if move_cost is not None:  # and unit.power >= move_cost + unit.action_queue_cost(game_state):
            cost = move_cost
            if len(unit.action_queue) and (
                (path.direction == unit.action_queue[0, 1] and unit.action_queue[0, 0] == 0)
                # or (self.task in ["ice", "ore"] and not path.avoid_collisions)
            ):
                self.logger.info("continue queue")
            else:
                self.actions = [unit.move(d, repeat=False, n=len(list(gr))) for d, gr in itertools.groupby(path.directions)][:20]
                cost += unit.action_queue_cost(game_state)
                self.manager.bot_targets[self.unit_id] = path.target
                self.logger.info(f"new queue {path.directions} {self.actions}")
            if unit.power >= cost:
                self.manager.botpos[unit.unit_id] = tuple(np.array(unit.pos) + move_deltas[path.direction])

    def _return_to_factory(self):
        """
        transfer resources and take power if unit in factory
        if not - move to it

        # TODO: action sequences. Transfer ore or ice first depending on task and/or quantity
        """
        unit = self.unit
        if self.adjacent_to_factory:
            self.task.action = "continue"
            if unit.cargo.ice > 0:
                self.actions = [unit.transfer(0, 0, unit.cargo.ice, repeat=False)]
                self.logger.info("transfer ice")
            elif unit.cargo.ore > 0:
                self.actions = [unit.transfer(0, 1, unit.cargo.ore, repeat=False)]
                self.logger.info("transfer ore")
            elif unit.power < self.battery_capacity * 0.1:
                self.actions = [unit.pickup(4, self.battery_capacity - unit.power)]
                self.logger.info("pickup power")
        else:
            self.task.action = "return"
            self.logger.info("move to factory")
            self._move_to([self.closest_factory_tile])
            if unit.unit_id in self.manager.bot_targets:
                self.manager.bot_targets.pop(unit.unit_id)

    def _task_ice(self):
        unit = self.unit
        game_state = self.game_state
        ice_locations = self.manager.ice_locations

        if (
            unit.cargo.ice < self.cargo_space
            and unit.power > unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.def_move_cost * self.distance_to_factory
            and not (self.factory.cargo.water <= (10 if self.game_state.is_day() else 20) and unit.cargo.ice)
            # and self.task.action != "return"
        ):
            # compute the distance to each ice tile from this unit and pick the closest

            # ice_rubbles = np.array([rubble_map[pos[0]][pos[1]] for pos in ice_locations])
            ice_distances = np.mean((ice_locations - unit.pos) ** 2, 1)  # - (ice_rubbles)*10
            sorted_ice = [ice_locations[k] for k in np.argsort(ice_distances)]
            # sorted_ice = self.assign_to_tile(ice_locations)
            # if we have reached the ice tile, start mining if possible
            if (ice_locations == unit.pos).all(1).any():
                if unit.power >= unit.dig_cost(game_state) + unit.action_queue_cost(game_state):
                    self.actions = [unit.dig(repeat=False)]
                    self.logger.info("reached ice, dig")

            else:
                self.logger.info("move to ice")
                self._move_to(sorted_ice)
        elif (
            unit.cargo.ice >= self.cargo_space
            or unit.power <= unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.def_move_cost * self.distance_to_factory
        ):
            self._return_to_factory()

    def _task_ore(self):
        unit = self.unit
        game_state = self.game_state
        ore_locations = self.manager.ore_locations
        if (
            unit.cargo.ore < self.cargo_space
            and unit.power > unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.def_move_cost * self.distance_to_factory
            # and self.task.action != "return"
        ):
            # compute the distance to each ore tile from this unit and pick the closest
            # ore_rubbles = np.array([rubble_map[pos[0]][pos[1]] for pos in ore_locations])
            ore_distances = np.mean((ore_locations - unit.pos) ** 2, 1)  # + (ore_rubbles)*2
            sorted_ore = [ore_locations[k] for k in np.argsort(ore_distances)]
            # sorted_ore = self.assign_to_tile(ore_locations)

            # if we have reached the ore tile, start mining if possible
            # if np.all(closest_ore == unit.pos):
            if (ore_locations == unit.pos).all(1).any():
                if unit.power >= unit.dig_cost(game_state) + unit.action_queue_cost(game_state):
                    self.actions = [unit.dig(repeat=False)]
                    self.logger.info("ore reached, dig")
            else:
                self.logger.info("move to ore")
                self._move_to(sorted_ore)

        elif (
            unit.cargo.ore >= self.cargo_space
            or unit.power <= unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.def_move_cost * self.distance_to_factory
        ):
            self._return_to_factory()

    def _task_rubble(self):
        unit = self.unit
        game_state = self.game_state
        rubble_locations = self.manager.rubble_locations

        if (
            unit.power
            > unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.rubble_dig_cost
            # and self.task.action != "return"
        ):
            # compute the distance to each rubble tile from this unit and pick the closest
            rubble_distances = np.mean((rubble_locations - unit.pos) ** 2, 1)

            sorted_rubble = [rubble_locations[k] for k in np.argsort(rubble_distances)]
            # sorted_rubble = self.assign_to_tile(rubble_locations)

            # if we have reached the rubble tile, start mining if possible
            if (rubble_locations == unit.pos).all(1).any():
                if unit.power >= unit.dig_cost(game_state) + unit.action_queue_cost(game_state):
                    self.actions = [unit.dig(repeat=False)]
                    self.logger.info("rubble reached, dig")

            else:
                # there was a check than rubble exists, but i believe this in nonsence in the actual game setup
                self._move_to(sorted_rubble)

        elif unit.power <= unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.rubble_dig_cost:
            self._return_to_factory()

    def _task_kill(self):
        # TODO: attack lichen
        unit = self.unit
        game_state = self.game_state

        opp_botpos = np.array([xy for xy in self.manager.opp_botpos if tuple(xy) not in self.manager.enemy_factory_tiles])

        if len(opp_botpos) != 0:
            opp_pos = np.array(opp_botpos).reshape(-1, 2)
            opponent_unit_distances = np.mean((opp_pos - unit.pos) ** 2, 1)
            min_distance = np.min(opponent_unit_distances)
            pos_min_distance = np.array(opp_pos[np.argmin(min_distance)])

            if min_distance == 1:
                self.logger.info("РЕЗНЯ")
                self._move_to([pos_min_distance])
            else:
                if unit.power > unit.action_queue_cost(game_state):
                    self.logger.info("move for attack")
                    self._move_to([pos_min_distance])
                else:
                    self._return_to_factory()
        else:
            self._task_rubble()

    def act(self):
        # Assigning task for the bot
        actions = {}

        unit_id = self.unit.unit_id
        unit = self.unit

        self.logger.info(f"{self.unit} current action queue: {self.unit.action_queue}, task: {self.manager.bots.get(unit_id)}")
        self.logger.info(f"botpos {self.manager.botpos}")

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

        task_method()

        if self.actions:
            actions = {unit_id: self.actions[:20]}
        return actions
