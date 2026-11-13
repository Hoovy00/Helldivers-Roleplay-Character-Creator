// Table house rules for item stats. Anything here is layered over the wiki
// snapshot in data/item-stats.js and survives re-running the build script.
//
// Use the item's exact catalog name. Only list the stats you want to change or
// add; everything else keeps its wiki value. You can also replace the
// description, or give an armor passive a custom description.
//
// Example:
//   "AR-23 Liberator": {
//     stats: { "Damage": "100 Ballistic", "Table Note": "Issued to every recruit" }
//   },
//   "B-01 Tactical": {
//     passiveDescription: "Counts as +1 AC while standing still."
//   },
//   "AR-23 Liberator": {
//     shotsPerAction: 8   // rounds one Fire action uses (default comes from fire rate)
//   },
//   "CQC-30 Stun Baton": {
//     weaponCategory: "Simple"   // Simple, Martial or Advanced; changes which proficiency it uses
//   },
//   "AR-2 Coyote": {
//     // Replaces the whole "Special effects & extra damage" list for this item.
//     effects: [
//       { title: "Status: Fire", stats: { "Damage": "50 Fire per turn", "Duration": "2 turns" } }
//     ]
//   },
window.FIELD_RECORD_ITEM_OVERRIDES = {
};
