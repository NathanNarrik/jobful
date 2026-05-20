import type { ApplicationStatus } from "@/types";

export const statusLabels: Record<ApplicationStatus, string> = {
  SAVED: "Saved",
  APPLIED: "Applied",
  PHONE_SCREEN: "Phone Screen",
  TECHNICAL: "Technical",
  FINAL: "Final Round",
  OFFER: "Offer",
  REJECTED: "Rejected",
};

export const statusOrder: ApplicationStatus[] = [
  "SAVED",
  "APPLIED",
  "PHONE_SCREEN",
  "TECHNICAL",
  "FINAL",
  "OFFER",
  "REJECTED",
];

export function titleCase(value: string) {
  return value
    .replaceAll("_", " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function daysSince(value: string | null) {
  if (!value) return "Fresh";
  const date = new Date(value);
  const diff = Date.now() - date.getTime();
  const days = Math.max(0, Math.floor(diff / 86_400_000));
  if (days === 0) return "Today";
  if (days === 1) return "1 day";
  return `${days} days`;
}

export function daysSinceLabel(value: string | null) {
  const age = daysSince(value);
  if (age === "Fresh") return "Fresh posting";
  if (age === "Today") return "Posted today";
  return `Posted ${age} ago`;
}

export function shortDate(value: string | null) {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

export function compactLocation(locations: string[]) {
  if (!locations.length) return "Unspecified";
  if (locations.length === 1) return locations[0];
  return `${locations[0]} +${locations.length - 1}`;
}

export function displayCompanyName(company: string) {
  const labels: Record<string, string> = {
    andurilindustries: "Anduril Industries",
    agilityrobotics: "Agility Robotics",
    akunacapital: "Akuna Capital",
    anaplan: "Anaplan",
    apptronik: "Apptronik",
    arcinstitute: "Arc Institute",
    airwallex: "Airwallex",
    abacus: "Abacus AI",
    alertmedia: "AlertMedia",
    alephalpha: "Aleph Alpha",
    applovin: "AppLovin",
    applied: "Applied Intuition",
    appomni: "AppOmni",
    apollographql: "Apollo GraphQL",
    arkoselabs: "Arkose Labs",
    augury: "Augury",
    automox: "Automox",
    avride: "Avride",
    axon: "Axon",
    altruist: "Altruist",
    angellist: "AngelList",
    a16z: "a16z",
    backblaze: "Backblaze",
    bloomreach: "Bloomreach",
    blockstream: "Blockstream",
    cabify: "Cabify",
    cargurus: "CarGurus",
    capellaspace: "Capella Space",
    cartahealthcare: "Carta Healthcare",
    catonetworks: "Cato Networks",
    censys: "Censys",
    chainguard: "Chainguard",
    clipboard: "Clipboard Health",
    coalition: "Coalition",
    colorhealth: "Color Health",
    commure: "Commure",
    cognite: "Cognite",
    connectwise: "ConnectWise",
    corelight: "Corelight",
    cresta: "Cresta",
    dmatrix: "d-Matrix",
    dailypay: "DailyPay",
    dapper: "Dapper Labs",
    dataiku: "Dataiku",
    deepl: "DeepL",
    delinea: "Delinea",
    descope: "Descope",
    devrev: "DevRev",
    dragos: "Dragos",
    five9: "Five9",
    flexe: "Flexe",
    freenome: "Freenome",
    geckorobotics: "Gecko Robotics",
    gocardless: "GoCardless",
    geotab: "Geotab",
    generalcatalyst: "General Catalyst",
    govini: "Govini",
    guild: "Guild",
    heygen: "HeyGen",
    hermeus: "Hermeus",
    hingehealth: "Hinge Health",
    hootsuite: "Hootsuite",
    imbue: "Imbue",
    includedhealth: "Included Health",
    invisible: "Invisible Technologies",
    jetbrains: "JetBrains",
    kickstarter: "Kickstarter",
    kodiak: "Kodiak",
    kong: "Kong",
    lightmatter: "Lightmatter",
    lithic: "Lithic",
    locusrobotics: "Locus Robotics",
    matillion: "Matillion",
    mapbox: "Mapbox",
    mercari: "Mercari",
    metabase: "Metabase",
    maymobility: "May Mobility",
    moderntreasury: "Modern Treasury",
    mozilla: "Mozilla",
    mural: "Mural",
    mystenlabs: "Mysten Labs",
    natera: "Natera",
    nasuni: "Nasuni",
    nerdwallet: "NerdWallet",
    netradyne: "Netradyne",
    nozominetworks: "Nozomi Networks",
    observeai: "Observe.AI",
    opengov: "OpenGov",
    outrider: "Outrider",
    oscar: "Oscar Health",
    pantherlabs: "Panther Labs",
    pathai: "PathAI",
    pipedrive: "Pipedrive",
    poshmark: "Poshmark",
    primer: "Primer",
    primerai: "Primer AI",
    public: "Public",
    purestorage: "Pure Storage",
    pubmatic: "PubMatic",
    redis: "Redis",
    relativity: "Relativity",
    secondfrontsystems: "Second Front Systems",
    shift4: "Shift4",
    smartsheet: "Smartsheet",
    sonarsource: "SonarSource",
    snorkelai: "Snorkel AI",
    socure: "Socure",
    scopely: "Scopely",
    serverobotics: "Serve Robotics",
    signoz: "SigNoz",
    sumologic: "Sumo Logic",
    supercell: "Supercell",
    taketwo: "Take-Two",
    tekion: "Tekion",
    thoughtmachine: "Thought Machine",
    trustpilot: "Trustpilot",
    uipath: "UiPath",
    voleon: "The Voleon Group",
    xero: "Xero",
    xometry: "Xometry",
    yubico: "Yubico",
    zoominfo: "ZoomInfo",
    betterment: "Betterment",
    beyondtrust: "BeyondTrust",
    billcom: "BILL",
    celonis: "Celonis",
    dialpad: "Dialpad",
    digitalocean98: "DigitalOcean",
    doordashusa: "DoorDash",
    fal: "fal",
    graphcore: "Graphcore",
    keepersecurity: "Keeper Security",
    knowbe4: "KnowBe4",
    lightningai: "Lightning AI",
    motional: "Motional",
    nebius: "Nebius",
    orcasecurity: "Orca Security",
    pingidentity: "Ping Identity",
    recordedfuture: "Recorded Future",
    remotecom: "Remote",
    rocketlab: "Rocket Lab",
    fiveringsllc: "Five Rings",
    hubspotjobs: "HubSpot",
    optiverus: "Optiver",
    stabilityai: "Stability AI",
    surveymonkey: "SurveyMonkey",
    tigergraph: "TigerGraph",
    sourcegraph91: "Sourcegraph",
    spacex: "SpaceX",
    spire: "Spire",
    stackblitz: "StackBlitz",
    stockx: "StockX",
    synthesia: "Synthesia",
    tenstorrent: "Tenstorrent",
    udio: "Udio",
    wayve: "Wayve",
    weightsandbiases: "Weights & Biases",
    weights_and_biases: "Weights & Biases",
    whatnot: "Whatnot",
    wizinc: "Wiz",
    worldlabs: "World Labs",
    zed: "Zed",
  };
  return labels[company] ?? company;
}

export function companyInitials(company: string) {
  const words = displayCompanyName(company).split(/\s+/).filter(Boolean);
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return words.slice(0, 2).map((word) => word[0]).join("").toUpperCase();
}

export function plainTextDescription(value: string | null) {
  if (!value) return "No description available.";
  return value
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>/gi, "\n\n")
    .replace(/<li>/gi, "\n- ")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&#x2019;|&rsquo;/g, "'")
    .replace(/&#x201C;|&ldquo;/g, '"')
    .replace(/&#x201D;|&rdquo;/g, '"')
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}
