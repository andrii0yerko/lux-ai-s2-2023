# Define helper functions
from itertools import chain
import numpy as np


def adjacent_indices(game_map, center_indices):
    # print(center_indices)
    rows, cols = center_indices
    indices = np.array([(rows - 1, cols), (rows + 1, cols), (rows, cols - 1), (rows, cols + 1)])
    mask = np.logical_and.reduce((np.all(indices >= 0, axis=1), indices[:, 0] < game_map.shape[0], indices[:, 1] < game_map.shape[1]))
    return indices[mask]


def simulate_factory_lichen_growth(factory_indices, lichen_map, game_map, n=1):
    """

    Args:
        factory_indices (np.ndarray): target factory tiles
        lichen_map (np.ndarray): lichen values (of specific strain)
        game_map (np.ndarray): 0 for free position, 1 - resources, rubble, factories
        n (int): steps to simulate

    Returns:
        np.ndarray: expected lichen map for the next turn
    """
    # factory_indices = game_map == 2
    for i in range(n):
        spread_indices = np.logical_and(lichen_map >= 20, game_map == 0)
        spread_indices = np.argwhere(spread_indices)

        current_mask = np.logical_and(lichen_map > 0, lichen_map < 100)

        empty_indices_lst = []
        for spread_idx in chain(spread_indices, factory_indices):
            # Seed lichen in adjacent empty cells
            adjacent_indices_list = adjacent_indices(game_map, spread_idx)
            empty_indices_mask = np.logical_and.reduce(
                (
                    adjacent_indices_list[:, 0] >= 0,
                    adjacent_indices_list[:, 0] < game_map.shape[0],
                    adjacent_indices_list[:, 1] >= 0,
                    adjacent_indices_list[:, 1] < game_map.shape[1],
                    game_map[tuple(adjacent_indices_list.T)] == 0,
                    lichen_map[tuple(adjacent_indices_list.T)] == 0,
                )
            )
            empty_indices = adjacent_indices_list[empty_indices_mask]

            empty_indices_lst.append(empty_indices)
        empty_indices = np.vstack(empty_indices_lst)

        lichen_map[tuple(empty_indices.T)] = 1
        lichen_map[current_mask] += 1

    return lichen_map


def simulate_lichen_growth(factories, game_state, n):

    estimate = {}

    for factory_id, factory in factories.items():
        estimate[factory_id] = np.where(game_state.board.lichen_strains == factory.strain_id, game_state.board.lichen_strains, 0)

    for _ in range(n):
        for factory_id, factory in factories.items():
            factory_indices = np.argwhere(game_state.board.factory_occupancy_map == factory.strain_id)
            game_map = np.add.reduce(
                [
                    game_state.board.rubble,
                    game_state.board.ice,
                    game_state.board.ore,
                    (game_state.board.factory_occupancy_map > -1).astype(int),
                    *estimate.values()
                ]
            )
            lichen_map = estimate[factory_id]

            estimate[factory_id] = simulate_factory_lichen_growth(factory_indices, game_map, lichen_map, n=1)

        # erase cell, which are going to be populated by two different strains
        lichen_occupation = np.add.reduce(list(map(lambda x: np.clip(x, 0, 1), estimate.values())))
        invalid_mask = lichen_occupation > 1
        for x in estimate.values():
            x[invalid_mask] = 0
        yield estimate
