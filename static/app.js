// Generated from climbtrack/src/lib/gender.ts — Czech first-name gender lists.
const FEMALE_NAMES = [
  "ada", "adela", "adéla", "adélie", "agáta", "alena", "alžběta", "amálie", "amelie", "ana",
  "anděla", "andrea", "aneta", "anežka", "anička", "anka", "anna", "barbora", "barča",
  "barunka", "beáta", "beta", "běta", "bianka", "blanka", "bohumila", "božena", "božka",
  "brunela", "cecilie", "cyriliena", "damiena", "daniela", "dara", "denisa", "deniska",
  "desislava", "dita", "dominika", "dorota", "draha", "drahuše", "dubravka", "edith", "edna",
  "eliška", "elen", "elena", "eleonora", "elisa", "emilie", "emily", "emma", "emílie", "erika",
  "estera", "eugenie", "eva", "evelína", "fanny", "filomena", "flóra", "františka", "gabriela",
  "gabina", "gertruda", "gita", "gréta", "hana", "hančka", "hanna", "heda", "helen", "helena",
  "henrieta", "hermina", "hilda", "ida", "ilona", "ingrid", "irena", "irina", "isabela",
  "iveta", "ivona", "izabela", "jarmila", "jasmína", "jehta", "jindra", "jindřiška", "jitka",
  "jitěnka", "johana", "josefina", "julie", "justýna", "karina", "karína", "karla", "karolína",
  "kateřina", "kačenka", "kazi", "kazimíra", "klementýna", "klára", "klaudie", "kristýna",
  "kristyna", "květa", "květoslava", "lada", "lara", "laura", "leona", "linda", "ludmila",
  "lucie", "lucinka", "luíza", "lída", "magdalena", "magdaléna", "marcela", "marie", "marta",
  "martina", "matylda", "melánie", "michaela", "mila", "milada", "milena", "miloslava",
  "miluše", "míša", "monika", "nadežda", "naděžda", "natálie", "nely", "nela", "nicola",
  "nikola", "nikol", "nina", "ofélie", "ofelie", "olena", "olžbeta", "patricie", "pavla",
  "penelopa", "petra", "petronela", "radana", "radmila", "radomíra", "rahela", "rebecca",
  "regina", "renata", "renáta", "richarda", "roberta", "rozálie", "růžena", "salome",
  "samuela", "sandra", "sára", "simona", "sofie", "sofia", "sona", "sonia", "sonka",
  "stanislava", "stela", "štěpánka", "tadeáška", "tamara", "tatiana", "tereza", "terezie",
  "terinka", "terezka", "tina", "tončka", "uliana", "ulrika", "valentina", "valérie", "vanda",
  "verika", "veronika", "verunka", "viktorie", "vilemína", "violeta", "viola", "vita", "vlasta",
  "vlastimila", "xenie", "zdeňka", "zdenka", "zdena", "zita", "zofie", "zuzana", "zuzanka",
  "žaneta", "žofie",
];
const MALE_NAMES = [
  "abel", "adam", "adolf", "alexandr", "alexander", "aleš", "albert", "alois", "andršt",
  "andrej", "antonín", "aron", "artur", "augustin", "benjamín", "benedikt", "bohumil",
  "bohuslav", "bojan", "boris", "bořivoj", "břetislav", "ctibor", "ctirad", "dalibor",
  "damian", "daniel", "daněš", "david", "denis", "dominik", "dušan", "eduard", "egon", "emil",
  "erik", "ernest", "eugen", "fabian", "ferdinand", "filip", "florián", "františek", "gabriel",
  "gustav", "hanuš", "herman", "hugo", "igor", "ilja", "iliáš", "inocenc", "isidor", "ivo",
  "ivoš", "ivan", "jakub", "jan", "jáchym", "jindřich", "jiří", "jozef", "josef", "julius",
  "justin", "kašpar", "klement", "koloman", "kristián", "kryštof", "kunhart", "kuneš",
  "leopold", "libor", "liboslav", "luděk", "ludvík", "lubomír", "lubor", "luboš", "marián",
  "mario", "marius", "martin", "matouš", "matěj", "matyáš", "maxmilián", "mečislav",
  "metoděj", "michal", "milan", "miloslav", "milota", "mirek", "miroslav", "mojmír",
  "nikita", "norbert", "oldřich", "oliver", "ondřej", "osvald", "oslav", "otto", "pavel",
  "patrik", "petr", "prokop", "purkart", "radim", "radomír", "radovan", "radoslav", "radek",
  "richard", "robert", "robin", "roman", "rostislav", "ruben", "rudolf", "samuel", "sebastian",
  "silvestr", "simon", "slaven", "slavomír", "stanislav", "šimon", "štědrý", "štěpán",
  "tadeáš", "teodor", "tibor", "tomáš", "urban", "václav", "vavřinec", "vendelín", "victor",
  "viktor", "vincent", "vítek", "vladimír", "vlastimil", "vlastislav", "vojtěch", "voršlík",
  "vratislav", "zbyšek", "zbyněk", "zdeněk", "zikmund", "zoroslav",
];
const MALE_A_NICKNAMES = [
  "kuba", "jirka", "jenda", "vojta", "tonda", "franta", "honza", "láďa", "pepa", "béďa",
  "míra", "kája", "fanda", "vencouš", "maty", "krista",
];

const VOWELS = "áaeěiouůyýé";

// Guess "holka" | "kluk" from a Czech first name (same rules as the original app).
function genderFromName(name) {
  const n = (name || "").trim().toLowerCase().replace(/\s+/g, "");
  if (!n) return null;
  if (FEMALE_NAMES.includes(n)) return "holka";
  if (MALE_NAMES.includes(n) || MALE_A_NICKNAMES.includes(n)) return "kluk";
  const first = n.split(/[^a-záčďéňóřůšťúžěíý]/i)[0] || "";
  if (FEMALE_NAMES.includes(first)) return "holka";
  if (MALE_NAMES.includes(first)) return "kluk";
  if (n.endsWith("ová") || n.endsWith("ů")) return "holka";
  const last = n[n.length - 1];
  if (last === "o") return "kluk";
  return VOWELS.includes(last) ? "holka" : "kluk";
}

function levelForYears(y) {
  return y > 4 ? "master" : y > 2 ? "mírně pokročilé" : "začátečník";
}

// Child forms: auto-pick gender while typing until the user clicks the toggle; show level.
document.querySelectorAll("form").forEach((form) => {
  const name = form.querySelector("[data-gender-auto]");
  if (!name) return;
  let touched = false;
  form.querySelectorAll("input[name=gender]").forEach((r) => r.addEventListener("change", () => (touched = true)));
  name.addEventListener("input", () => {
    const g = !touched && genderFromName(name.value);
    if (g) form.querySelector(`input[name=gender][value="${g}"]`).checked = true;
  });
  const years = form.querySelector("[data-level-preview]");
  const out = form.querySelector("[data-level-out]");
  const show = () => (out.textContent = years.value === "" ? "" : `Úroveň: ${levelForYears(Number(years.value))}`);
  years.addEventListener("input", show);
  show();
});

// Confirm before destructive submits (data-confirm on the form or on the clicked button).
document.addEventListener("submit", (e) => {
  const msg = e.submitter?.dataset.confirm || e.target.dataset.confirm;
  if (msg && !confirm(msg)) e.preventDefault();
});

// Lezík task rows: fixed slots, hidden + disabled ones are not submitted (a hidden id with no title = delete).
document.querySelectorAll(".task-rows").forEach((box) => {
  const rows = [...box.querySelectorAll(".task-row")];
  const setRow = (row, on) => {
    row.hidden = !on;
    row.querySelectorAll("input:not([type=hidden])").forEach((i) => (i.disabled = !on));
  };
  box.querySelector("[data-add-row]").addEventListener("click", () => {
    const next = rows.find((r) => r.hidden && !r.dataset.removed);
    if (next) setRow(next, true);
  });
  rows.forEach((row) =>
    row.querySelector("[data-remove-row]").addEventListener("click", () => {
      if (rows.filter((r) => !r.hidden).length <= 1) return;
      setRow(row, false);
      if (row.querySelector("input[type=hidden]").value) row.dataset.removed = "1"; // keep slot so its id gets deleted
    }),
  );
});

// Děti: live search, filters and sorting.
const kids = document.getElementById("kids");
if (kids) {
  const state = { day: "", time: "", level: "", sort: "" };
  const search = document.getElementById("search");
  const items = [...kids.querySelectorAll("a.item")];
  const apply = () => {
    const s = search.value.toLowerCase();
    let shown = 0;
    for (const el of items) {
      const d = el.dataset;
      const ok = d.name.includes(s) && (!state.day || d.day === state.day) &&
        (!state.time || d.time === state.time) && (!state.level || d.level === state.level);
      el.hidden = !ok;
      shown += ok;
    }
    document.getElementById("none").hidden = shown > 0;
    const key = state.sort.replace("-", "");
    const dir = state.sort.startsWith("-") ? -1 : 1;
    // Array.sort is stable, so equal values keep the server's name order.
    const sorted = key ? [...items].sort((a, b) => dir * (a.dataset[key] - b.dataset[key])) : items;
    kids.prepend(...sorted);
    const n = ["day", "time", "level", "sort"].filter((k) => state[k]).length;
    document.getElementById("filter-count").textContent = n || "";
  };
  document.querySelectorAll("[data-filter]").forEach((group) =>
    group.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      const k = group.dataset.filter;
      state[k] = state[k] === b.dataset.v && k !== "sort" ? "" : b.dataset.v;
      group.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x.dataset.v === state[k]));
      apply();
    }),
  );
  search.addEventListener("input", apply);
}

// Fade out flash messages.
setTimeout(() => document.querySelectorAll(".toast").forEach((t) => t.remove()), 3500);
