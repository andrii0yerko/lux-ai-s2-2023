import logging
import networkx as nx
import numpy as np

from scipy.ndimage import binary_dilation

from lux.kit import GameState
from lux.unit import move_deltas
from lux.utils import direction_to


def get_3x3_indices(pos):
    indices = np.indices((3, 3)) - 1  # create array of indices with center at (1,1)
    shift = pos.reshape(-1, 1, 1)  # reshape shift array for broadcasting
    indices = indices + shift  # shift indices to center at (x,y)
    indices = indices.reshape(2, -1).T  # flatten indices and return as Nx2 array
    return indices


class MapManager:
    def __init__(self, player, game_state) -> None:
        self.player = player
        self.opp_player = "player_1" if self.player == "player_0" else "player_0"
        self.refresh(game_state=game_state)

    def _build_graph(self, game_state):
        G = nx.DiGraph()

        def add_delta(a):
            return tuple(np.array(a[0]) + np.array(a[1]))

        logging.info("%s", game_state.factories[self.opp_player])

        rubbles = game_state.board.rubble
        for x in range(rubbles.shape[0]):
            for y in range(rubbles.shape[1]):
                cost = rubbles[x, y]
                if (x, y) in self.enemy_factory_tiles:
                    cost = 10_000

                G.add_node((x, y), rubble=cost)

        deltas = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        for g1 in G.nodes:
            x1, y1 = g1
            for delta in deltas:
                g2 = add_delta((g1, delta))
                if G.has_node(g2):
                    G.add_edge(g1, g2, cost=20 + rubbles[g2])
        return G

    def shortest_path(self, pos_from, pos_to):
        if np.all(pos_from == pos_to):
            return [0]
        path = np.array(nx.shortest_path(self._graph, source=tuple(pos_from), target=tuple(pos_to), weight="cost"))
        return [direction_to(a, b) for a, b in zip(path[:-1], path[1:])]

    def shortest_path_cost(self, pos_from, pos_to):
        path = nx.shortest_path(self._graph, source=tuple(pos_from), target=tuple(pos_to), weight="cost")
        return nx.path_weight(self._graph, path, "cost")

    def get_closest_factory(self, pos):
        factory_distances = np.mean((self.factory_tiles - pos) ** 2, 1)
        min_index = np.argmin(factory_distances)
        closest_factory_tile = self.factory_tiles[min_index]
        closest_factory_id = self.factory_ids[min_index]
        return closest_factory_id, closest_factory_tile

    def get_vulnerable_enemies(self):
        opp_botpos = np.array([xy for xy in self.opp_botpos.values() if tuple(xy) not in self.enemy_factory_tiles])
        return opp_botpos

    def get_robot_by_pos(self, pos):
        for unit in self.game_state.units[self.opp_player].values():
            if np.all(np.equal(pos, unit.pos)):
                return unit

    def get_enemy_lichen_borders(self):
        opponent_strains = [x.strain_id for x in self.game_state.factories[self.opp_player].values()]
        opponent_lichen = np.isin(self.game_state.board.lichen_strains, opponent_strains)
        struct = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])
        # Dilate the nonzero elements
        dilated = binary_dilation(opponent_lichen, structure=struct).astype(int)

        # Subtract the original nonzero elements from the dilated elements
        border = dilated - opponent_lichen
        return np.argwhere(border)

    def get_tiles_to_clean(self):
        rubble = np.vstack([self.rubble_locations.reshape(-1, 2), self.opponent_lichen_locations.reshape(-1, 2)])

        enemy_borders = self.get_enemy_lichen_borders()

        resources = np.vstack([self.ice_locations, self.ore_locations, enemy_borders])
        mask = ~(rubble[:, None] == resources).all(axis=2).any(axis=1)
        return rubble[mask]

    def get_tiles_distances(self, pos, kind, distance="l1"):
        mapping = {
            "ice": self.ice_locations,
            "ore": self.ore_locations,
            "rubble": self.tiles_to_clean,
            "enemy": self.get_vulnerable_enemies(),
            "opponent_lichen": self.opponent_lichen_locations,
        }
        locations = mapping[kind]
        if not len(locations):
            return [], []

        if distance == "l1":
            distances = np.sum(np.abs(locations - pos), 1)
        elif distance == "l2":
            distances = np.mean((locations - pos) ** 2, 1)
        elif distance == "cost":  # too expensive to compute
            distances = np.array([self.shortest_path_cost(pos, loc) for loc in locations])
        idx = np.argsort(distances)
        return locations[idx], distances[idx]

    def check_collision(self, pos, direction, unit_type="LIGHT"):
        unitpos = set(self.botpos.values())

        new_pos = pos + move_deltas[direction]

        if unit_type == "LIGHT":
            return tuple(new_pos) in unitpos or tuple(new_pos) in self.botposheavy.values()
        else:
            return tuple(new_pos) in unitpos

    def refresh(self, game_state: GameState):
        self.game_state = game_state
        self.enemy_factory_tiles = {
            tuple(xy) for factory in game_state.factories[self.opp_player].values() for xy in get_3x3_indices(factory.pos).tolist()
        }
        self._graph = self._build_graph(game_state)

        # Unit locations
        self.botpos = {}
        self.botposheavy = {}
        self.opp_botpos = {}
        for player in [self.player, self.opp_player]:
            for unit_id, unit in game_state.units[player].items():
                if player == self.player:
                    self.botpos[unit_id] = tuple(unit.pos)
                else:
                    self.opp_botpos[unit_id] = tuple(unit.pos)

                if unit.unit_type == "HEAVY":
                    self.botposheavy[unit_id] = tuple(unit.pos)

        factory_tiles = []
        # factory_units = []
        factory_ids = []
        factories = game_state.factories[self.player]

        for unit_id, factory in factories.items():
            factory_tiles += [factory.pos]
            # factory_units += [factory]
            factory_ids += [unit_id]

        factory_tiles = np.array(factory_tiles)  # Factory locations (to go back to)
        self.factory_tiles = factory_tiles
        # self.factory_units = factory_units
        self.factory_ids = factory_ids
        self.factories = game_state.factories[self.player]

        # Resource map and locations
        ice_map = game_state.board.ice
        ore_map = game_state.board.ore
        rubble_map = game_state.board.rubble

        ice_locations_all = np.argwhere(ice_map >= 1)  # numpy position of every ice tile
        ore_locations_all = np.argwhere(ore_map >= 1)  # numpy position of every ore tile
        rubble_locations_all = np.argwhere(rubble_map >= 1)  # numpy position of every rubble tile

        self.ice_locations = ice_locations_all
        self.ore_locations = ore_locations_all
        self.rubble_locations = rubble_locations_all
        self.rubble_map = rubble_map

        opponent_strains = [x.strain_id for x in game_state.factories[self.opp_player].values()]
        self.opponent_lichen_locations = np.argwhere(np.isin(game_state.board.lichen_strains, opponent_strains))

        self.tiles_to_clean = self.get_tiles_to_clean()
