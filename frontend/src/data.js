export const SAMPLE_PRODUCTS = [
  {
    id: "sellbird-core",
    name: "Sellbird Core",
    company: "Sellbird AI",
    website: "sellbird.example",
    pricing: "$149–$499 / month",
    targetMarket: "B2B SaaS · 50–500 employees",
    icpTags: ["Revenue Operations", "SaaS", "50–500 employees"],
    description: "Local-first sales intelligence for focused B2B teams.",
    benefits: ["Evidence-backed research", "Private local inference", "Reviewable email drafts"],
    icpCriteria: "B2B software teams with a small RevOps function and a clear local-data requirement.",
    prospects: 48,
    researched: 40,
    drafts: 13,
    averageScore: 78,
    weeklyProspects: 7,
    isPreview: true,
  },
  {
    id: "enterprise-api",
    name: "Enterprise API",
    company: "Sellbird AI",
    website: "api.sellbird.example",
    pricing: "Custom",
    targetMarket: "Fintech · 100–2,000 employees",
    icpTags: ["Partnerships", "API-first", "Fintech"],
    description: "Partner onboarding and API workflow intelligence.",
    benefits: ["Partner-fit scoring", "Saved-page research", "Consistent follow-up drafts"],
    icpCriteria: "Fintech and infrastructure businesses expanding partner integrations.",
    prospects: 36,
    researched: 30,
    drafts: 9,
    averageScore: 83,
    weeklyProspects: 5,
    isPreview: true,
  },
  {
    id: "outbound-kit",
    name: "Outbound Kit",
    company: "Sellbird AI",
    website: "outbound.sellbird.example",
    pricing: "$79 / month",
    targetMarket: "B2B services · 20–250 employees",
    icpTags: ["Founder-led", "Services", "Outbound"],
    description: "A focused research and drafting workflow for small outbound teams.",
    benefits: ["Prospect prioritization", "Source snippets", "Human-reviewed drafts"],
    icpCriteria: "Owner-led B2B service firms that need a repeatable, low-volume workflow.",
    prospects: 31,
    researched: 26,
    drafts: 8,
    averageScore: 72,
    weeklyProspects: 4,
    isPreview: true,
  },
  {
    id: "workflow-studio",
    name: "Workflow Studio",
    company: "Sellbird AI",
    website: "studio.sellbird.example",
    pricing: "$199 / month",
    targetMarket: "Health technology · 50–1,000 employees",
    icpTags: ["Customer Operations", "Health Tech", "Workflow"],
    description: "Local-first workflow research for teams with complex customer operations.",
    benefits: ["Saved evidence", "Local task queue", "Consistent team context"],
    icpCriteria: "Health technology companies hiring customer operations and implementation roles.",
    prospects: 27,
    researched: 22,
    drafts: 8,
    averageScore: 71,
    weeklyProspects: 2,
    isPreview: true,
  },
];

export const SAMPLE_PROSPECTS = [
  {
    id: "P-1042",
    productId: "sellbird-core",
    company: "Acme Technologies",
    contact: "Maya Chen",
    role: "Director, Revenue Operations",
    domain: "acme.example",
    industry: "B2B SaaS",
    score: 90,
    updatedAt: "Today · 9:10 AM",
    status: "Completed",
    signals: 3,
    summary: "A growing RevOps team is consolidating fragmented workflows across its sales stack.",
    evidence: "The preview dossier includes a recent RevOps leadership hire, a systems-consolidation initiative, and increased sales-team hiring. Verify each source before using this context.",
    sourceLinks: ["Company overview · saved page text", "Careers page · saved page text", "Product page · saved page text"],
    isPreview: true,
  },
  {
    id: "P-1038",
    productId: "enterprise-api",
    company: "FinStack",
    contact: "Omar Patel",
    role: "VP, Growth & Partnerships",
    domain: "finstack.example",
    industry: "Financial Technology",
    score: 84,
    updatedAt: "Today · 8:42 AM",
    status: "Completed",
    signals: 2,
    summary: "Recent API expansion points to a need for higher-volume partner onboarding.",
    evidence: "Preview research connects expanded integration coverage and a growing partnerships team. The saved source passages should be reviewed before creating an Email Draft.",
    sourceLinks: ["Partner API page · saved page text", "Open roles · saved page text"],
    isPreview: true,
  },
  {
    id: "P-1034",
    productId: "outbound-kit",
    company: "Nova Systems",
    contact: "Riley Morgan",
    role: "Chief Operating Officer",
    domain: "novasystems.example",
    industry: "Logistics",
    score: 85,
    updatedAt: "Yesterday · 4:26 PM",
    status: "Completed",
    signals: 2,
    summary: "Regional operations hiring suggests manual handoffs are becoming a bottleneck.",
    evidence: "The saved-page preview highlights regional team growth and increased coordination work. Source passages are shown separately from AI synthesis.",
    sourceLinks: ["Operations page · saved page text", "Careers page · saved page text"],
    isPreview: true,
  },
  {
    id: "P-1029",
    productId: "workflow-studio",
    company: "Brightpath Health",
    contact: "Priya Nair",
    role: "VP, Customer Experience",
    domain: "brightpath.example",
    industry: "Health Technology",
    score: 68,
    updatedAt: "Yesterday · 2:03 PM",
    status: "Running",
    signals: 1,
    summary: "A new customer-operations role points to a focus on workflow consistency.",
    evidence: "The sample research is still processing saved page text. Confirm the underlying source details before creating an Email Draft.",
    sourceLinks: ["Customer experience page · saved page text"],
    isPreview: true,
  },
  {
    id: "P-1021",
    productId: "enterprise-api",
    company: "LegacyCorp",
    contact: "Daniel Brooks",
    role: "Head of Sales Operations",
    domain: "legacy.example",
    industry: "Enterprise Software",
    score: 52,
    updatedAt: "Mon · 11:48 AM",
    status: "Failed",
    signals: 0,
    summary: "Saved-page research timed out; retry the local scrape to complete this record.",
    evidence: "The preview page fetch timed out before an evidence record was complete. Retry the saved-text workflow before using this prospect in outreach.",
    sourceLinks: ["Saved page text · unavailable in preview"],
    isPreview: true,
  },
];

export const SAMPLE_TASKS = [
  {
    id: "TASK-2084",
    title: "Prospect research · Acme Technologies",
    type: "Qwen3 research",
    prospectId: "P-1042",
    productId: "sellbird-core",
    status: "Completed",
    duration: "00:18",
    detail: "Three preview buying signals saved for review.",
    updatedAt: "2 min ago",
    isPreview: true,
  },
  {
    id: "TASK-2083",
    title: "Saved-page capture · FinStack",
    type: "Playwright scrape",
    prospectId: "P-1038",
    productId: "enterprise-api",
    status: "Running",
    duration: "00:07",
    detail: "Reading locally stored source text.",
    updatedAt: "Running now",
    isPreview: true,
  },
  {
    id: "TASK-2079",
    title: "Saved-page capture · LegacyCorp",
    type: "Playwright scrape",
    prospectId: "P-1021",
    productId: "enterprise-api",
    status: "Failed",
    duration: "01:00",
    detail: "Request timed out before saved text was complete.",
    updatedAt: "18 min ago",
    isPreview: true,
  },
];

export const SAMPLE_DRAFTS = [
  {
    id: "D-3014",
    productId: "sellbird-core",
    prospectId: "P-1042",
    subject: "A question about your RevOps workflow",
    body: "Hi Maya,\n\nI noticed your team is consolidating revenue operations workflows. I have a short, source-backed overview of how local research can help teams prioritize that work without moving prospect data to a hosted AI service.\n\nWould it be useful to take a look?\n\nBest,\nYour name",
    savedAt: "Today · 9:25 AM",
    isPreview: true,
  },
  {
    id: "D-3013",
    productId: "enterprise-api",
    prospectId: "P-1038",
    subject: "Partner onboarding at FinStack",
    body: "Hi Omar,\n\nYour recent API expansion stood out. I have a concise overview of a local-first way to research partner fit and keep the evidence close to the team.\n\nWould a short summary be useful?\n\nBest,\nYour name",
    savedAt: "Today · 8:50 AM",
    isPreview: true,
  },
  {
    id: "D-3012",
    productId: "outbound-kit",
    prospectId: "P-1034",
    subject: "Regional operations handoffs",
    body: "Hi Riley,\n\nI saw the regional operations hiring on your team. I have a short overview of ways small teams can organize local prospect research and review each outreach draft before it is used.\n\nWould that be helpful?\n\nBest,\nYour name",
    savedAt: "Yesterday · 4:41 PM",
    isPreview: true,
  },
  {
    id: "D-3011",
    productId: "workflow-studio",
    prospectId: "P-1029",
    subject: "Customer operations workflows",
    body: "Hi Priya,\n\nYour customer operations role caught my attention. I have a short summary on keeping research evidence and draft review in one local workflow.\n\nWould you be open to a brief overview?\n\nBest,\nYour name",
    savedAt: "Yesterday · 2:20 PM",
    isPreview: true,
  },
];

export const SAMPLE_INBOUND_REPLIES = [
  {
    id: "SAMPLE-R-01",
    prospectId: "P-1042",
    text: "Sounds useful. Could you send me a short overview of how the local research workflow works?",
    label: "interested",
    confidence: 0.91,
    rationale: "The reply asks to see a product overview.",
    createdAt: "Preview example",
    isPreview: true,
  },
  {
    id: "SAMPLE-R-02",
    prospectId: "P-1038",
    text: "Could we meet next Tuesday afternoon to talk through partner onboarding?",
    label: "meeting_request",
    confidence: 0.94,
    rationale: "The reply explicitly proposes a meeting time.",
    createdAt: "Preview example",
    isPreview: true,
  },
  {
    id: "SAMPLE-R-03",
    prospectId: "P-1034",
    text: "Please remove me from your outreach list. Thanks.",
    label: "unsubscribe",
    confidence: 0.98,
    rationale: "The reply asks to stop contact.",
    createdAt: "Preview example",
    isPreview: true,
  },
];

// Seeded examples are explicitly marked separately from user-imported preview rows.
for (const records of [SAMPLE_PRODUCTS, SAMPLE_PROSPECTS, SAMPLE_TASKS, SAMPLE_DRAFTS, SAMPLE_INBOUND_REPLIES]) {
  records.forEach((record) => {
    record.isSample = true;
    record.isImported = false;
  });
}

export const ACTIVITY_SERIES = {
  "Last 7 days": [
    { label: "Nov 17", researched: 18, drafts: 7 },
    { label: "Nov 18", researched: 25, drafts: 11 },
    { label: "Nov 19", researched: 31, drafts: 13 },
    { label: "Nov 20", researched: 28, drafts: 12 },
    { label: "Nov 21", researched: 36, drafts: 16 },
    { label: "Nov 22", researched: 39, drafts: 17 },
    { label: "Nov 23", researched: 42, drafts: 19 },
  ],
  "Last 30 days": [
    { label: "Nov 02", researched: 22, drafts: 10 },
    { label: "Nov 06", researched: 28, drafts: 12 },
    { label: "Nov 10", researched: 35, drafts: 15 },
    { label: "Nov 14", researched: 39, drafts: 17 },
    { label: "Nov 18", researched: 42, drafts: 19 },
    { label: "Nov 23", researched: 48, drafts: 22 },
  ],
};

export function parseCsv(input) {
  const records = [];
  let row = [];
  let cell = "";
  let quoted = false;
  const text = String(input ?? "").replace(/^\uFEFF/, "");

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else if (character === '"') {
        quoted = false;
      } else {
        cell += character;
      }
    } else if (character === '"' && cell.length === 0) {
      quoted = true;
    } else if (character === ",") {
      row.push(cell);
      cell = "";
    } else if (character === "\n") {
      row.push(cell.replace(/\r$/, ""));
      records.push(row);
      row = [];
      cell = "";
    } else {
      cell += character;
    }
  }
  if (cell.length || row.length) {
    row.push(cell.replace(/\r$/, ""));
    records.push(row);
  }
  const aliases = {
    company: "company_name",
    organization: "company_name",
    organization_name: "company_name",
    contact: "contact_name",
    name: "contact_name",
    title: "contact_title",
    role: "contact_title",
    domain: "company_domain",
    website: "company_domain",
    email: "contact_email",
    employees: "employee_count",
    employees_count: "employee_count",
    headcount: "employee_count",
    page_path: "page_text_path",
  };
  const headers = (records.shift() || []).map((header) => {
    const normalized = header.trim().toLowerCase().replace(/[\s-]+/g, "_");
    return aliases[normalized] || normalized;
  });
  if (!headers.length || !headers.includes("company_name")) {
    throw new Error("CSV needs a company, organization, or company_name column.");
  }
  const rows = records
    .filter((values) => values.some((value) => String(value).trim()))
    .map((values) => Object.fromEntries(headers.map((header, index) => [header, (values[index] ?? "").trim()])));
  return { headers, rows };
}

export function csvEscape(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}
