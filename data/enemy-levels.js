// Enemy levels for the Enemies page, measured against the level guide in the Character builder:
//   0–1  conscripts and fodder (below a freshly trained SEAF soldier)
//   1    freshly trained          2  veteran soldier         3  elite specialist / new Helldiver
//   4–5  prodigy / veteran Helldiver                         6–8 heroic, mythic feats
//   9    augmented legend (the player cap)                   10+ colossal threats beyond any one person
// Players top out at level 9, so anything above 9 is a boss to be beaten with stratagems, weak points and teamwork.
// Edit freely: an enemy missing from this list falls back to its minimum game difficulty − 1.
window.FIELD_RECORD_ENEMY_LEVELS = {
  // ---- Terminids ----
  "Scavenger": 0, "Pouncer": 0, "Shrieker": 1, "Hunter": 1, "Warrior": 1,
  "Hive Guard": 2, "Alpha Warrior": 3, "Nursing Spewer": 3,
  "Brood Commander": 4, "Stalker": 4,
  "Alpha Commander": 5,
  "Charger": 6, "Charger Behemoth": 7, "Impaler": 8,
  "Bile Titan": 9, "Dragonroach": 9,
  "Hive Lord": 12,
  // Terminid strains (the wiki renamed the Bile units to Caustic Strain; old names kept for saved encounters)
  "Caustic Spitter": 0, "Caustic Warrior": 3, "Caustic Spewer": 4, "Caustic Charger": 7,
  "Bile Spitter": 0, "Bile Warrior": 3, "Bile Spewer": 4, "Spore Charger": 7,
  "Noxious Scavenger": 0, "Noxious Spewer": 4,
  "Predator Hunter": 2, "Predator Stalker": 5,
  "Rupture Warrior": 3, "Rupture Spewer": 5, "Rupture Charger": 7,
  "Spore Burst Scavenger": 0, "Spore Burst Hunter": 1, "Spore Burst Warrior": 2, "Spore Burst Bile Titan": 9,

  // ---- Automatons ----
  "Trooper": 1, "Assault Raider": 1, "Brawler": 1, "MG Raider": 1, "Rocket Raider": 1,
  "Commissar": 2, "Marauder": 2,
  "Berserker": 3, "Devastator": 3,
  "Heavy Devastator": 4, "Rocket Devastator": 4, "Scout Strider": 4,
  "Reinforced Scout Strider": 5,
  "Gunship": 6, "Hulk Bruiser": 6, "Hulk Scorcher": 6,
  "Hulk Obliterator": 7, "Dropship": 7,
  "Annihilator Tank": 8, "Shredder Tank": 8, "Barrager Tank": 8, "War Strider": 8,
  "Factory Strider": 10,
  // Automaton legions
  "Pyro Trooper": 2, "Incendiary Rocket Raider": 2,
  "Conflagration Devastator": 4, "Incendiary MG Devastator": 4, "Hulk Firebomber": 6,
  "Jet Brigade Trooper": 2, "Jet Brigade MG Raider": 2, "Jet Brigade Commissar": 3,
  "Jet Brigade Devastator": 4, "Jet Brigade Hulk Bruiser": 7, "Jet Brigade Hulk Scorcher": 7,
  "Agitator": 2, "Radical": 3, "Vox Engine": 10,

  // ---- Illuminate ----
  "Voteless": 0, "Watcher": 2,
  "Overseer": 3, "Elevated Overseer": 3, "Crescent Overseer": 3,
  "Stingray": 6, "Harvester": 7, "Fleshmob": 7, "Warp Ship": 7,
  "Leviathan": 11, "Illuminate Overship": 12,
  "Wretch": 1, "Crusher": 7,
  "Obtruder": 2, "Gatekeeper": 6, "Veracitor": 6
};
