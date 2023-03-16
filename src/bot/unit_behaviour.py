import itertools
import logging

import numpy as np
from bot.logging import BehaviourLoggingAdapter
from bot.state_manager import StateManager
from lux.kit import GameState
from lux.unit import Unit


class UnitBehaviour:
    def __init__(self, unit: Unit, game_state: GameState, manager: StateManager):
        self.unit = unit
        self.game_state = game_state
        self.manager = manager

        logger = logging.getLogger(__class__.__name__)

        # Create adapter with custom prefix
        self.logger = BehaviourLoggingAdapter(logger, {"real_env_steps": self.game_state.real_env_steps, "unit_id": self.unit.unit_id})

        unit_cfg = self.game_state.env_cfg.ROBOTS[unit.unit_type]
        self.battery_capacity = unit_cfg.BATTERY_CAPACITY
        self.cargo_space = unit_cfg.CARGO_SPACE
        self.def_move_cost = unit_cfg.MOVE_COST
        self.rubble_dig_cost = unit_cfg.DIG_COST

        self.actions = []

    def get_direction(self, unit, closest_tile, sorted_tiles):
        closest_tile = np.array(closest_tile)
        # direction = direction_to(np.array(unit.pos), closest_tile)
        directions = self.manager.shortest_path(unit.pos, closest_tile)
        direction = directions[0]
        k = 0
        unit_type = unit.unit_type
        while self.manager.check_collision(np.array(unit.pos), direction, unit_type) and k < min(len(sorted_tiles) - 1, 500):
            k += 1
            closest_tile = sorted_tiles[k]
            closest_tile = np.array(closest_tile)
            # direction = direction_to(np.array(unit.pos), closest_tile)
            directions = self.manager.shortest_path(unit.pos, closest_tile)
            direction = directions[0]

        if self.manager.check_collision(unit.pos, direction, unit_type):
            for direction_x in np.arange(4, -1, -1):
                if not self.manager.check_collision(np.array(unit.pos), direction_x, unit_type):
                    direction = direction_x
                    directions = [direction]
                    break

        if self.manager.check_collision(np.array(unit.pos), direction, unit_type):
            direction = np.random.choice(np.arange(5))
            directions = [direction]

        move_deltas = np.array([[0, 0], [0, -1], [1, 0], [0, 1], [-1, 0]])

        self.manager.botpos[unit.unit_id] = str(np.array(unit.pos) + move_deltas[direction])
        self.logger.info(f"{unit.pos}, {closest_tile}, directions, {directions}")

        return direction, directions

    def _move_to(self, tile, sorted_alternatives):
        unit = self.unit
        game_state = self.game_state

        direction, directions = self.get_direction(unit, tile, sorted_alternatives)
        move_cost = unit.move_cost(game_state, direction)
        # check move_cost is not None, meaning that direction is not blocked
        # check if unit has enough power to move and update the action queue.
        if move_cost is not None and unit.power >= move_cost + unit.action_queue_cost(game_state):
            if len(unit.action_queue) and directions[0] == unit.action_queue[0, 1] and unit.action_queue[0, 0] == 0:
                self.logger.info("continue queue")
            else:
                self.actions = [unit.move(d, repeat=False, n=len(list(gr))) for d, gr in itertools.groupby(directions)][:20]

                self.logger.info(f"new queue {directions} {self.actions}")

    def _return_to_factory(self):
        """
        transfer resources and take power if unit in factory
        if not - move to it

        # TODO: action sequences. Transfer ore or ice first depending on task and/or quantity
        """
        unit = self.unit
        if self.adjacent_to_factory:
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
            self.logger.info("move to factory")
            self._move_to(self.closest_factory_tile, [self.closest_factory_tile])

    def _task_ice(self):
        unit = self.unit
        game_state = self.game_state
        ice_locations = self.manager.ice_locations

        if (
            unit.cargo.ice < self.cargo_space
            and unit.power > unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.def_move_cost * self.distance_to_factory
        ):
            # compute the distance to each ice tile from this unit and pick the closest

            # ice_rubbles = np.array([rubble_map[pos[0]][pos[1]] for pos in ice_locations])
            ice_distances = np.mean((ice_locations - unit.pos) ** 2, 1)  # - (ice_rubbles)*10
            sorted_ice = [ice_locations[k] for k in np.argsort(ice_distances)]

            closest_ice = sorted_ice[0]
            # if we have reached the ice tile, start mining if possible
            if np.all(closest_ice == unit.pos):
                if unit.power >= unit.dig_cost(game_state) + unit.action_queue_cost(game_state):
                    self.actions = [unit.dig(repeat=False)]
                    self.logger.info("reached ice, dig")

            else:
                self.logger.info("move to ice")
                self._move_to(closest_ice, sorted_ice)

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
        ):
            # compute the distance to each ore tile from this unit and pick the closest
            # ore_rubbles = np.array([rubble_map[pos[0]][pos[1]] for pos in ore_locations])
            ore_distances = np.mean((ore_locations - unit.pos) ** 2, 1)  # + (ore_rubbles)*2
            sorted_ore = [ore_locations[k] for k in np.argsort(ore_distances)]

            closest_ore = sorted_ore[0]
            # if we have reached the ore tile, start mining if possible
            if np.all(closest_ore == unit.pos):
                if unit.power >= unit.dig_cost(game_state) + unit.action_queue_cost(game_state):
                    self.actions = [unit.dig(repeat=False)]
                    self.logger.info("ore reached, dig")
            else:
                self.logger.info("move to ore")
                self._move_to(closest_ore, sorted_ore)

        elif (
            unit.cargo.ore >= self.cargo_space
            or unit.power <= unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.def_move_cost * self.distance_to_factory
        ):
            self._return_to_factory()

    def _task_rubble(self):
        unit = self.unit
        game_state = self.game_state
        rubble_locations = self.manager.rubble_locations

        if unit.power > unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.rubble_dig_cost:
            # compute the distance to each rubble tile from this unit and pick the closest
            rubble_distances = np.mean((rubble_locations - unit.pos) ** 2, 1)
            sorted_rubble = [rubble_locations[k] for k in np.argsort(rubble_distances)]
            closest_rubble = sorted_rubble[0]

            # if we have reached the rubble tile, start mining if possible
            if np.all(closest_rubble == unit.pos) or self.manager.rubble_map[unit.pos[0], unit.pos[1]] != 0:
                if unit.power >= unit.dig_cost(game_state) + unit.action_queue_cost(game_state):
                    self.actions = [unit.dig(repeat=False)]
                    self.logger.info("rubble reached, dig")

            else:
                # there was a check than rubble exists, but i believe this in nonsence in the actual game setup
                self._move_to(closest_rubble, sorted_rubble)

        elif unit.power <= unit.action_queue_cost(game_state) + unit.dig_cost(game_state) + self.rubble_dig_cost:
            self._return_to_factory()

    def _task_kill(self):
        # TODO: attack lichen
        unit = self.unit
        game_state = self.game_state

        if len(self.manager.opp_botpos) != 0:
            opp_pos = np.array(self.manager.opp_botpos).reshape(-1, 2)
            opponent_unit_distances = np.mean((opp_pos - unit.pos) ** 2, 1)
            min_distance = np.min(opponent_unit_distances)
            pos_min_distance = np.array(opp_pos[np.argmin(min_distance)])

            if min_distance == 1:
                self.logger.info("РЕЗНЯ")
                self._move_to(pos_min_distance, [pos_min_distance])
            else:
                if unit.power > unit.action_queue_cost(game_state):
                    self.logger.info("move for attack")
                    self._move_to(pos_min_distance, [pos_min_distance])
                else:
                    self._return_to_factory()

    def act(self):
        # Assigning task for the bot
        actions = {}

        unit_id = self.unit.unit_id
        unit = self.unit

        self.logger.info(f"{self.unit} current action queue: {self.unit.action_queue}, task: {self.manager.bots.get(unit_id)}")

        self.closest_factory_tile = self.manager.register_bot(unit_id, unit)
        self.distance_to_factory = np.mean(np.subtract(self.closest_factory_tile, unit.pos) ** 2)
        self.adjacent_to_factory = self.distance_to_factory <= 1

        if unit.power < unit.action_queue_cost(self.game_state):
            self.logger.info("no power, skip")
            return {}

        task = self.manager.get_bot_task(unit_id)
        task_method = {
            "ice": self._task_ice,
            "ore": self._task_ore,
            "rubble": self._task_rubble,
            "kill": self._task_kill,
        }[task]

        task_method()

        if self.actions:
            actions = {unit_id: self.actions[:20]}
        return actions
