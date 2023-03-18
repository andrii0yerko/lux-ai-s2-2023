import logging

import numpy as np
from bot.logging import BehaviourLoggingAdapter
from bot.state_manager import StateManager
from lux.factory import Factory
from lux.kit import GameState


class FactoryBehaviour:
    min_bots = {"ice": 5, "ore": 5, "rubble": 5, "kill": 1}

    def __init__(self, factory: Factory, game_state: GameState, manager: StateManager):
        self.factory = factory
        self.game_state = game_state
        self.manager = manager
        self.robots = self.manager.get_factory_bots(self.factory.unit_id)

        logger = logging.getLogger(__class__.__name__)
        self.logger = BehaviourLoggingAdapter(logger, {"real_env_steps": self.game_state.real_env_steps, "unit_id": self.factory.unit_id})

        self.robot_cfg = self.game_state.env_cfg.ROBOTS

    def _under_attack(self):
        if not len(self.manager.opp_botpos):
            return False
        opp_pos = np.array(self.manager.opp_botpos).reshape(-1, 2)
        opponent_unit_distances = np.mean((opp_pos - self.factory.pos) ** 2, 1)
        min_distance = np.min(opponent_unit_distances)
        self._closest_enemy = opp_pos[np.argmin(opponent_unit_distances)]
        return min_distance < 15

    def _have_defender(self):
        if not len(self.robots["defend"]):
            return False
        return True

    def _next_task(self):
        minbot_task = None

        # NO. BOTS PER TASK
        for task in ["kill", "ice", "ore", "rubble"]:
            num_bots = len(self.robots[task]) + sum([task in self.manager.factory_queue[self.factory.unit_id]])
            if num_bots < self.min_bots[task]:
                # minbots = num_bots
                minbot_task = task
                break
        if not self.robots["ice"]:
            minbot_task = "ice"
        elif not self.robots["ore"]:
            minbot_task = "ore"
        return minbot_task

    def _assign_defenders(self):
        preference = "HEAVY"

        # check if desired bot type available
        all_factory_bots = sum(self.robots.values(), start=[])

        heavies = {}
        for x in all_factory_bots:
            x_type = "HEAVY" if x in self.manager.botposheavy else "LIGHT"
            if x_type == preference:
                heavies[x] = self.manager.botposheavy[x]

        if not heavies:
            return False

        heavies_ids = list(heavies)
        heavies_pos = np.array(list(heavies.values()))

        unit_distances = np.mean((self._closest_enemy - heavies_pos) ** 2, 1)
        defender = heavies_ids[np.argmin(unit_distances)]

        self.manager.bots[defender] = "defend"
        return True

    def _revoke_defenders(self):
        resid = {task: num - len(self.robots[task]) for task, num in self.min_bots.items()}

        for x in self.robots["defend"]:
            if resid["ice"]:
                self.manager.bots[x] = "ice"
                resid["ice"] -= 1
            elif resid["ore"]:
                self.manager.bots[x] = "ore"
                resid["ore"] -= 1
            else:
                self.manager.bots[x] = "rubble"

    def act(self):
        actions = {}
        unit_id = self.factory.unit_id
        game_state = self.game_state
        factory = self.factory

        self.next_bot_task = self._next_task()

        under_attack = self._under_attack()
        have_defenders = self._have_defender()

        if under_attack and not have_defenders:
            success = self._assign_defenders()
            if not success:
                self.next_bot_task = "defend"
        if not under_attack and have_defenders:
            self._revoke_defenders()

        if self.next_bot_task is not None:
            # if minbot_task in ["kill"]:
            #     if factory.power >= self.robot_cfg["HEAVY"].POWER_COST and factory.cargo.metal >= self.robot_cfg["HEAVY"].METAL_COST:
            #         actions = {unit_id: factory.build_heavy()}
            if self.next_bot_task in ["kill", "defend", "ice"]:
                if factory.power >= self.robot_cfg["HEAVY"].POWER_COST and factory.cargo.metal >= self.robot_cfg["HEAVY"].METAL_COST:
                    actions = {unit_id: factory.build_heavy()}
                elif factory.power >= self.robot_cfg["LIGHT"].POWER_COST and factory.cargo.metal >= self.robot_cfg["LIGHT"].METAL_COST:
                    actions = {unit_id: factory.build_light()}
            else:
                if factory.power >= self.robot_cfg["LIGHT"].POWER_COST and factory.cargo.metal >= self.robot_cfg["LIGHT"].METAL_COST:
                    actions = {unit_id: factory.build_light()}
                elif factory.power >= self.robot_cfg["HEAVY"].POWER_COST and factory.cargo.metal >= self.robot_cfg["HEAVY"].METAL_COST:
                    actions = {unit_id: factory.build_heavy()}

            # task = FactoryTask(task=self.minbot_task)
            self.manager.factory_queue[unit_id].append(self.next_bot_task)

        step = game_state.real_env_steps
        if factory.can_water(game_state) and step > 800 and factory.cargo.water > (1000 - step) + 100:
            actions = {unit_id: factory.water()}

        return actions
