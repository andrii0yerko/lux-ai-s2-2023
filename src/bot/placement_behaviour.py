import numpy as np
from lux.utils import my_turn_to_place_factory


class PlacementBehaviour:
    def __init__(self, game_state, manager):
        self.faction_names = {"player_0": "TheBuilders", "player_1": "FirstMars"}
        self.game_state = game_state
        self.manager = manager
        self.player = self.manager.player
        self.opp_player = self.manager.opp_player

    def _bid(self):
        actions = {}
        actions["faction"] = self.faction_names[self.player]
        actions["bid"] = 5  # Learnable
        return actions

    def _place_factory(self):
        actions = dict()
        game_state = self.game_state
        # Factory placement period
        # optionally convert observations to python objects with utility functions
        opp_factories = [f.pos for _, f in game_state.factories[self.opp_player].items()]
        my_factories = [f.pos for _, f in game_state.factories[self.player].items()]

        # how much water and metal you have in your starting pool to give to new factories
        water_left = game_state.teams[self.player].water
        metal_left = game_state.teams[self.player].metal

        # how many factories you have left to place
        factories_to_place = game_state.teams[self.player].factories_to_place
        if factories_to_place > 0:
            # we will spawn our factory in a random location with 100 metal n water (learnable)
            potential_spawns = np.array(list(zip(*np.where(game_state.board.valid_spawns_mask == 1))))

            ice_map = game_state.board.ice
            ore_map = game_state.board.ore
            ice_tile_locations = np.argwhere(ice_map == 1)  # numpy position of every ice tile
            ore_tile_locations = np.argwhere(ore_map == 1)  # numpy position of every ice tile

            min_dist = 10e6
            best_loc = potential_spawns[0]

            d_rubble = 10

            for loc in potential_spawns:
                ice_tile_distances = np.mean((ice_tile_locations - loc) ** 2, 1)
                ore_tile_distances = np.mean((ore_tile_locations - loc) ** 2, 1)
                density_rubble = np.mean(
                    game_state.board.rubble[
                        max(loc[0] - d_rubble, 0) : min(loc[0] + d_rubble, 47), max(loc[1] - d_rubble, 0) : max(loc[1] + d_rubble, 47)
                    ]
                )

                closes_opp_factory_dist = 0
                if len(opp_factories) >= 1:
                    closes_opp_factory_dist = np.min(np.mean((np.array(opp_factories) - loc) ** 2, 1))
                closes_my_factory_dist = 0
                if len(my_factories) >= 1:
                    closes_my_factory_dist = np.min(np.mean((np.array(my_factories) - loc) ** 2, 1))

                minimum_ice_dist = (
                    np.min(ice_tile_distances) * 10
                    + 0.01 * np.min(ore_tile_distances)
                    + 10 * density_rubble / (d_rubble)
                    - closes_opp_factory_dist * 0.1
                    + closes_my_factory_dist * 0.01
                )

                if minimum_ice_dist < min_dist:
                    min_dist = minimum_ice_dist
                    best_loc = loc

            #                 spawn_loc = potential_spawns[np.random.randint(0, len(potential_spawns))]
            spawn_loc = best_loc
            actions["spawn"] = spawn_loc
            actions["metal"] = min(300, metal_left) if factories_to_place > 1 else metal_left
            actions["water"] = min(300, water_left) if factories_to_place > 1 else water_left
        return actions

    def act(self, step):
        if step == 0:
            return self._bid()
        elif my_turn_to_place_factory(self.game_state.teams[self.player].place_first, step):
            return self._place_factory()

        return {}
