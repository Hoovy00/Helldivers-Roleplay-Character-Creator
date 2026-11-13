# Helldivers Roleplay Character Creator

A character builder and GM toolkit for a Discord roleplay set in the Helldivers 2 universe, using rules adapted from Pathfinder 2e.

## For players

1. Open the site and build your Helldiver: abilities, skills, proficiencies and loadout.
2. Your character saves automatically in your own browser (nothing is uploaded anywhere).
3. When you're done, press **Export JSON** and send the downloaded file to your GM.

## For the GM

- **Import JSON** (in the Character bar) adds a player's exported file to your roster. Several files can be imported at once.
- **Squad view** shows every imported character side by side.
- The **Enemies** page has the enemy library, encounter builder, initiative tracker, mission tracker and enemy attacks against the squad.

## Data

Weapon, armor, stratagem and enemy stats come from the [Helldivers Wiki](https://helldivers.wiki.gg) (CC BY-SA 4.0), bundled in `data/` so the site works offline. `tools/build_item_stats.py` refreshes them after a game update. House-rule changes go in `data/item-overrides.js` and `data/enemy-levels.js`.

Fan project, not affiliated with Arrowhead Game Studios or Sony Interactive Entertainment.
