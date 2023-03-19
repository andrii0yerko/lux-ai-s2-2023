import logging
import os
from bot.factory_behaviour import FactoryBehaviour
from bot.placement_behaviour import PlacementBehaviour
from bot.unit_behaviour import UnitBehaviour

from lux.kit import obs_to_game_state, EnvConfig
import numpy as np


from .state_manager import StateManager


logger = logging.getLogger()
logger.setLevel(os.environ.get("LOGLEVEL", "CRITICAL"))  # to disable logging on leaderboard

formatter = logging.Formatter("%(levelname)s - %(message)s")
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


class Agent:
    def __init__(self, player: str, env_cfg: EnvConfig) -> None:
        self.player = player
        self.opp_player = "player_1" if self.player == "player_0" else "player_0"
        np.random.seed(0)
        self.env_cfg: EnvConfig = env_cfg

        self.manager = StateManager(self.player)

    def early_setup(self, step: int, obs, remainingOverageTime: int = 60):
        """
        Early Phase
        place bid, then place factories
        """
        game_state = obs_to_game_state(step, self.env_cfg, obs)
        return PlacementBehaviour(game_state, self.manager).act(step)

    def _act_factories(self, game_state):
        actions = {}
        factories = game_state.factories[self.player]

        for unit_id, factory in factories.items():
            logger.info(f"{game_state.real_env_steps}, {unit_id}")
            actions.update(FactoryBehaviour(factory, game_state, self.manager).act())

        return actions

    def _act_robots(self, game_state):
        actions = {}
        units = game_state.units[self.player]

        for unit_id, unit in sorted(units.items()):
            actions.update(UnitBehaviour(unit, game_state, self.manager).act())

        return actions

    def act(self, step: int, obs, remainingOverageTime: int = 60):
        """
        1. Regular Phase
        2. Building Robots
        """

        actions = dict()
        game_state = obs_to_game_state(step, self.env_cfg, obs)
        self.manager.refresh(game_state)

        # build robots
        actions.update(self._act_factories(game_state))

        # move robots
        actions.update(self._act_robots(game_state))

        logger.info(f"{game_state.real_env_steps}, {actions}")
        return actions
