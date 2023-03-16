from collections import defaultdict
import networkx as nx
import numpy as np

from lux.kit import GameState
from lux.utils import direction_to


class StateManager:
    move_deltas = np.array([[0, 0], [0, -1], [1, 0], [0, 1], [-1, 0]])

    def __init__(self, player) -> None:
        self.player = player
        self.opp_player = "player_1" if self.player == "player_0" else "player_0"

        self.bots = {}
        self.botpos = []
        self.bot_factory = {}
        self.factory_bots = defaultdict(
            lambda: {
                "ice": [],
                "ore": [],
                "rubble": [],
                "kill": [],
            }
        )
        self.factory_queue = defaultdict(list)

    def _build_graph(self, game_state):
        G = nx.Graph()

        def add_delta(a):
            return tuple(np.array(a[0]) + np.array(a[1]))

        rubbles = game_state.board.rubble
        for x in range(rubbles.shape[0]):
            for y in range(rubbles.shape[1]):
                G.add_node((x, y), rubble=rubbles[x, y])

        deltas = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        for g1 in G.nodes:
            x1, y1 = g1
            for delta in deltas:
                g2 = add_delta((g1, delta))
                if G.has_node(g2):
                    G.add_edge(g1, g2, cost=20 + rubbles[g2])
        return G

    def shortest_path(self, pos_from, pos_to):
        path = np.array(nx.shortest_path(self._graph, source=tuple(pos_from), target=tuple(pos_to), weight="cost"))
        return [direction_to(a, b) for a, b in zip(path[:-1], path[1:])]

    def check_collision(self, pos, direction, unit_type="LIGHT"):
        unitpos = set(self.botpos.values())

        move_deltas = np.array([[0, 0], [0, -1], [1, 0], [0, 1], [-1, 0]])

        new_pos = pos + move_deltas[direction]

        if unit_type == "LIGHT":
            return str(new_pos) in unitpos or str(new_pos) in self.botposheavy.values()
        else:
            return str(new_pos) in unitpos

    def get_factory_bots(self, unit_id):
        for task in ["ice", "ore", "rubble", "kill"]:
            for bot_unit_id in self.factory_bots[unit_id][task]:
                if bot_unit_id not in self.botpos.keys():
                    self.factory_bots[unit_id][task].remove(bot_unit_id)
        return self.factory_bots[unit_id]

    def register_bot(self, unit_id, unit):
        """
        assign bot to the closest factory
        """
        factory_tiles = self.factory_tiles
        factory_ids = self.factory_ids
        factories = self.factories

        if unit_id not in self.bots.keys():
            self.bots[unit_id] = ""

        if unit_id not in self.bot_factory.keys():
            factory_distances = np.mean((factory_tiles - unit.pos) ** 2, 1)
            min_index = np.argmin(factory_distances)
            closest_factory_tile = factory_tiles[min_index]
            self.bot_factory[unit_id] = factory_ids[min_index]
        elif self.bot_factory[unit_id] not in factory_ids:
            factory_distances = np.mean((factory_tiles - unit.pos) ** 2, 1)
            min_index = np.argmin(factory_distances)
            closest_factory_tile = factory_tiles[min_index]
            self.bot_factory[unit_id] = factory_ids[min_index]
        else:
            closest_factory_tile = factories[self.bot_factory[unit_id]].pos
        return closest_factory_tile

    def get_bot_task(self, unit_id):
        if self.bots[unit_id] == "":
            task = "ice"
            if len(self.factory_queue[self.bot_factory[unit_id]]) != 0:
                task = self.factory_queue[self.bot_factory[unit_id]].pop(0)
            self.bots[unit_id] = task
            self.factory_bots[self.bot_factory[unit_id]][task].append(unit_id)
            # print(self.game_state.real_env_steps, unit_id, "new task", task)
        return self.bots[unit_id]

    def refresh(self, game_state: GameState):
        self._graph = self._build_graph(game_state)

        # Unit locations
        self.botpos = {}
        self.botposheavy = {}
        self.opp_botpos = []
        for player in [self.player, self.opp_player]:
            for unit_id, unit in game_state.units[player].items():
                if player == self.player:
                    self.botpos[unit_id] = str(unit.pos)
                else:
                    self.opp_botpos.append(unit.pos)

                if unit.unit_type == "HEAVY":
                    self.botposheavy[unit_id] = str(unit.pos)

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
