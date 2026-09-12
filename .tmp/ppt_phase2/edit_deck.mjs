import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const input = ".tmp/ppt_phase2/template-starter.pptx";
const output = "/Users/gayathridevi/Projects/loanlens/Bank_Loan_Processing_Phase2_Review1_Enhanced.pptx";
const presentation = await PresentationFile.importPptx(await FileBlob.load(input));
const inspected = await presentation.inspect({
  kind: "slide,textbox",
  include: "id,slide,name,text",
  maxChars: 100000
});
const lines = inspected.ndjson.trim().split(/\n+/).map(JSON.parse);

const copy = {
  16: {
    "Text 0": "PHASE 2 ENHANCEMENT · LLM / RAG",
    "Text 1": "LLM & RAG Enhancement Priorities",
    "Text 2": "RETRIEVAL & GROUNDING",
    "Text 5": "Hybrid search: BM25 + embeddings with metadata filters",
    "Text 8": "Rerank retrieved evidence before sending context to the LLM",
    "Text 11": "Return document, page and section citations with every answer",
    "Text 14": "Separate extracted facts, inference and uncertainty clearly",
    "Text 16": "AGENTS, SAFETY & EVALUATION",
    "Text 19": "Focused Document, Verification, Financial and Compliance agents",
    "Text 22": "Measure Recall@K, MRR, groundedness and citation accuracy",
    "Text 25": "Track hallucination, contradiction, latency and decision errors",
    "Text 28": "Prompt-injection defence plus a human approval gate",
    "Text 30": "Immediate priority: hybrid RAG plus a Verification Agent to reduce unsupported answers and document contradictions.",
    "Text 32": "16 / 17"
  },
  17: {
    "Text 0": "PHASE 2 DELIVERY · FRONTEND",
    "Text 1": "Frontend Enhancements Completed",
    "Text 5": "Search & Pagination",
    "Text 6": "Functional application search with API-backed pagination.",
    "Text 10": "Responsive Navigation",
    "Text 11": "Mobile menu, simplified controls and light / dark theme.",
    "Text 15": "Upload Experience",
    "Text 16": "Multi-file upload with applicant, loan type and feedback.",
    "Text 20": "Dashboard Accuracy",
    "Text 21": "Monthly values scoped to year with clearer date labels.",
    "Text 25": "Analytics & Export",
    "Text 26": "Smaller graph markers, analytics charts and CSV export.",
    "Text 30": "Screenshot Placeholder",
    "Text 31": "Capture the localhost UI and paste the screenshot over this card.",
    "Text 33": "17 / 17"
  }
};

for (const [slideNumberText, replacements] of Object.entries(copy)) {
  const slideNumber = Number(slideNumberText);
  const records = lines.filter((x) => x.slide === slideNumber && x.kind === "textbox");
  for (const [name, nextText] of Object.entries(replacements)) {
    const record = records.find((x) => x.name === name);
    if (!record) throw new Error(`Missing ${name} on slide ${slideNumber}`);
    const slide = presentation.slides.items[slideNumber - 1];
    const target = slide.elements.items.find((element) => element.name === name);
    if (!target) throw new Error(`Missing editable element ${name} on slide ${slideNumber}`);
    target.text.replace(record.text, nextText);
  }
}

const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(output);
console.log(output);
