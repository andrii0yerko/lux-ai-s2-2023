from collections import defaultdict
from dataclasses import dataclass
import logging
import networkx as nx
import numpy as np

from lux.kit import GameState
from lux.utils import direction_to


def get_3x3_indices(pos):
    indices = np.indices((3, 3)) - 1  # create array of indices with center at (1,1)
    shift = pos.reshape(-1, 1, 1)  # reshape shift array for broadcasting
    indices = indices + shift  # shift indices to center at (x,y)
    indices = indices.reshape(2, -1).T  # flatten indices and return as Nx2 array
    return indices


@dataclass
class RobotTask:
    task: str
    action: str = None


# TODO
# This dict + id logic is a mess
# Use classes and references instead.
class StateManager:
    move_deltas = np.array([[0, 0], [0, -1], [1, 0], [0, 1], [-1, 0]])

    def __init__(self, player) -> None:
        self.player = player
        self.opp_player = "player_1" if self.player == "player_0" else "player_0"

        self.bots = {}
        self.botpos = []
        self.bot_factory = {}
        self.bot_targets = {}
        self.factory_queue = defaultdict(list)

    def _build_graph(self, game_state):
        G = nx.Graph()

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
        path = np.array(nx.shortest_path(self._graph, source=tuple(pos_from), target=tuple(pos_to), weight="cost"))
        return [direction_to(a, b) for a, b in zip(path[:-1], path[1:])]

    def check_collision(self, pos, direction, unit_type="LIGHT"):
        unitpos = set(self.botpos.values())

        move_deltas = np.array([[0, 0], [0, -1], [1, 0], [0, 1], [-1, 0]])

        new_pos = pos + move_deltas[direction]

        if unit_type == "LIGHT":
            return tuple(new_pos) in unitpos or tuple(new_pos) in self.botposheavy.values()
        else:
            return tuple(new_pos) in unitpos

    def get_factory_bots(self, unit_id):
        result = defaultdict(list)
        for bot, factory in self.bot_factory.items():
            if bot not in self.botpos.keys():
                continue
            if factory != unit_id:
                continue
            task = self.bots.get(bot)
            result[task.task].append(bot)
        return result

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
            logging.info("%s, assign new task, len queue %s", unit_id, len(self.factory_queue[self.bot_factory[unit_id]]))
            if len(self.factory_queue[self.bot_factory[unit_id]]) != 0:
                task = self.factory_queue[self.bot_factory[unit_id]].pop(0)
            self.bots[unit_id] = RobotTask(task)
            # self.factory_bots[self.bot_factory[unit_id]][task].append(unit_id)
            # print(self.game_state.real_env_steps, unit_id, "new task", task)
        return self.bots[unit_id]

    def refresh(self, game_state: GameState):
        self.enemy_factory_tiles = {
            tuple(xy) for factory in game_state.factories[self.opp_player].values() for xy in get_3x3_indices(factory.pos).tolist()
        }
        self._graph = self._build_graph(game_state)

        # Unit locations
        self.botpos = {}
        self.botposheavy = {}
        self.opp_botpos = []
        for player in [self.player, self.opp_player]:
            for unit_id, unit in game_state.units[player].items():
                if player == self.player:
                    self.botpos[unit_id] = tuple(unit.pos)
                else:
                    self.opp_botpos.append(unit.pos)

                if unit.unit_type == "HEAVY":
                    self.botposheavy[unit_id] = tuple(unit.pos)

        self.bot_targets = {k: v for k, v in self.bot_targets.items() if k in self.botpos}

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
