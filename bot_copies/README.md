# Collection of reference agents

Here stored agents that I had used for changes benchmarking. By chance, it also represents step-by-step evolution of my agent.

| Name | Description| Score\* |
|---|---|---|
|  `v0_orig` | [Original open-source bot](https://www.kaggle.com/code/scakcotf/building-a-basic-rule-based-agent-in-python) by https://www.kaggle.com/scakcotf | 908 (~1000, if set bid to 5) |
| `v1_reduce_penalty` | place nonzero bid and factories closer to opponent, earlier lichen growing, and also some random modifications, that are still very buggy at this moment | 1060 (even higher, if set 0.1 bonus from closeness)
| `v2_collision_avoider` | finally use sequences for moving without collisions, also add defend task | 1175 |
| `v3_ore_resiter` | Ice+rubble robots only, reuse sequences if possible | 1130 (lb shift) |
| `v4_rubble_commuter` | Minimalistic fights logic for all the robots, limited rubble neighborhood to dig, which appearn in an interesting lights behaviour | 1235 (final score) |

\* - at the time when submission plays. Not really represents something because of huge leaderboard shift at the last weeks of competition