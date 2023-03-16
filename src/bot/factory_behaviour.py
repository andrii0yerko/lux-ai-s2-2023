import logging
from bot.logging import BehaviourLoggingAdapter
from bot.state_manager import StateManager
from lux.factory import Factory
from lux.kit import GameState


class FactoryBehaviour:
    def __init__(self, factory: Factory, game_state: GameState, manager: StateManager):
        self.factory = factory
        self.game_state = game_state
        self.manager = manager

        logger = logging.getLogger(__class__.__name__)
        self.logger = BehaviourLoggingAdapter(logger, {"real_env_steps": self.game_state.real_env_steps, "unit_id": self.factory.unit_id})

        self.robot_cfg = self.game_state.env_cfg.ROBOTS

    def act(self):
        actions = {}
        unit_id = self.factory.unit_id
        game_state = self.game_state
        factory = self.factory

        factory_bots = self.manager.get_factory_bots(unit_id)

        minbot_task = None
        min_bots = {"ice": 5, "ore": 5, "rubble": 5, "kill": 1}
        # NO. BOTS PER TASK
        for task in ["kill", "ice", "ore", "rubble"]:
            num_bots = len(factory_bots[task]) + sum([task in self.manager.factory_queue[unit_id]])  # FIXME
            if num_bots < min_bots[task]:
                # minbots = num_bots
                minbot_task = task
                break

        if minbot_task is not None:
            if minbot_task in ["kill", "ice"]:
                if factory.power >= self.robot_cfg["HEAVY"].POWER_COST and factory.cargo.metal >= self.robot_cfg["HEAVY"].METAL_COST:
                    actions = {unit_id: factory.build_heavy()}
                elif factory.power >= self.robot_cfg["LIGHT"].POWER_COST and factory.cargo.metal >= self.robot_cfg["LIGHT"].METAL_COST:
                    actions = {unit_id: factory.build_light()}
            else:
                if factory.power >= self.robot_cfg["LIGHT"].POWER_COST and factory.cargo.metal >= self.robot_cfg["LIGHT"].METAL_COST:
                    actions = {unit_id: factory.build_light()}
                elif factory.power >= self.robot_cfg["HEAVY"].POWER_COST and factory.cargo.metal >= self.robot_cfg["HEAVY"].METAL_COST:
                    actions = {unit_id: factory.build_heavy()}

            self.manager.factory_queue[unit_id].append(minbot_task)

        step = game_state.real_env_steps
        if factory.can_water(game_state) and step > 800 and factory.cargo.water > (1000 - step) + 100:
            actions = {unit_id: factory.water()}

        return actions
