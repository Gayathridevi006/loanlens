import { FileBlob, PresentationFile } from "@oai/artifact-tool";
const p=await PresentationFile.importPptx(await FileBlob.load("/Users/gayathridevi/Downloads/Bank_Loan_Processing_Phase2_Review1_GayathriDeviB.pptx"));
const x=await p.inspect({kind:"slide,textbox,shape",include:"id,slide,name,bbox,text,textPreview",maxChars:100000});
console.log(x.ndjson);
