# Collection of reference agents

| Name | Description| Score\* |
|---|---|---|
|  `v0_orig` | [Original open-source bot](https://www.kaggle.com/code/scakcotf/building-a-basic-rule-based-agent-in-python) by https://www.kaggle.com/scakcotf | 908 (~1000, if set bid to 5) |
| `v1_reduce_penalty` | place nonzero bid and factories closer to opponent, earlier lichen growing, and also some random modifications, that are still very buggy at this moment | 1060 (even higher, if set 0.1 bonus fro closeness)
| `v2_collision_avoider` | finally use sequences for moving without collisions, also add defend task | 1175 |

\* - at the time when submission plays