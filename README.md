# Lux AI Season 2
Solution for [Lux AI Season 2](https://www.kaggle.com/competitions/lux-ai-season-2) simulation competition on Kaggle.

A basic rule-based agent which achieved 76th place (bronze medal range) with a score of 1235.5

## About the competition
> The Lux AI Challenge is a competition where competitors design agents to tackle a multi-variable optimization, resource gathering, and allocation problem in a 1v1 scenario against other competitors. In addition to optimization, successful agents must be capable of analyzing their opponents and developing appropriate policies to get the upper hand.

In this challenge, competitors had to develop agents to play the zero-sum turn-based two-player strategy game. The agent had to control robots to dig rubble and gather resources, and factories to build robots and grow lichen. A player with the higher lichen amount at the turn of 1000 wins.

See [Specifications](https://www.kaggle.com/competitions/lux-ai-season-2/overview/lux-ai-specifications) for more details

## Approach
The solution is a rule-based agent improved from the [scakcotf baseline](https://www.kaggle.com/code/scakcotf/building-a-basic-rule-based-agent-in-python) consisting of mostly predefined factory behavior, and somewhat dynamic robots reaction for the environment.

### Early stage
Taken from the baseline with almost no changes.

Bid 5 then place all the factories by simple heuristic to score each possible spawn location based on:
- rubble density
- distance to the closest ice
- distance to the closest ore
- distance to the closest opponent factory
- distance to the closest player factory

### Main stage: Factories
Factories first build robots and assign their tasks based on the predefined sequence then mostly stay inactive during the game. They also detect opponent appearances nearby and assign a robot to defend the area.
Starting from turn 800 factory grows lichen, if it has enough water to do it all the following turns (determined by a simple heuristic).

The final agent does not heavily rely upon economics and does not dig ore or generate power. Only a few robots are built - one heavy and 4-5 light, which allows them to not experience a severe lack of power, but survive till the end if no intervention occurs, and prepare enough space for lichen growth.

### Main stage: Robots

- Each robot belongs to a particular factory, which is its place to return gathered resources and take power. 
- Robots have one of the tasks given by the factory and obey the logic it determines. 
- Every robot reacts to opponent closeness: try to destroy the enemy robot if can, and escape to the safe zone otherwise

- Paths for robots are built using graph shortest path algorithm as described in [this notebook by jtbontinck](https://www.kaggle.com/code/jtbontinck/shortest-path-on-mars-using-networkx).
 
- Collision avoidance was handled in “real-time”, every robot check if it can move further, and if the cell was already occupied - change its direction.

- Actions were computed each turn, and action sequences were used for power usage optimization. The robot creates a sequence of all the following actions determined by its task, then compares the new sequence with the existing one: if the first action is the same, the queue was not overwritten.

#### Tasks: Ice
Task handled by the first heavy robots. Simply digs the closest ice, and return to the factory to transfer it if the cargo is full and takes power. Additionally, urgent transfer was added: if the factory is out of water, and the robot has ice in the cargo - it returns back immediately.

#### Tasks: Rubble
Handled by light robots - digs closest rubble or enemy lichen, returns to factory if discharged.
A few restrictions were added:
- ignore rubble on resource tiles
- ignore tiles that prevent opponent lichen from spreading
- consider rubble tiles only in a specific radius around the factory, or adjacent to lichen.
- if there is no rubble to dig - wait near the radius border to prevent crowding

The last two restrictions, which were originally added to prevent robots from digging too far from the factory, accidentally result in some interesting behavior - when their base cleaning is done, robots start to help other factories with cleaning, and massively attack enemy lichen.

Actually, these features help to do the last score gain and stay in the bronze.

#### Tasks: Ore
Same as ice: find the closest resource - dig - back to the factory to unload and recharge. Was not used in the final agent.

#### Tasks: Kill
The logic for an attacking robot - find go to the closest opponent robot, and try to fight it with common simple fights logic. Was not used in the final agent.

#### Tasks: Defend
The same code as Kill, but treated by the factory differently. When the opponent robot appears close to the factory - one of the factory heavies changes its task to defend and tries to strike the enemy. If the enemy was destroyed or had left the factory area - all defenders were revoked back to normal tasks.

## Summary

A few things I have learned during the competition:

- Rule-based approach is extremely fun
- Bugs. Bugs everywhere. All the time during the competition I have the higher gain not by implementing features, but by making them actually work!
- Code organization really matters. Suboptimal code organization - suboptimal agent logic. Keep it in mind, and don't be like me 😄


## Repository content
- [`Taskfile.yaml`](https://taskfile.dev/) - Management of basic project actions (make a submission, run game, etc)
- `src/` - source code for the latest agent version
- `bot_copies/` - previous milestone versions of the agent, used to measure modifications improvement
- `tools/` - third-party tools (actually only [luxai_s2_ab by mogbymo](https://www.kaggle.com/competitions/lux-ai-season-2/discussion/389473)) and some (unfinished) code unrelated to the agent.


