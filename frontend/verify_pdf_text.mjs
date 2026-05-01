import * as pdfjs from 'pdfjs-dist/legacy/build/pdf.mjs';
import fs from 'fs';

async function verifyPdf(filePath, pageNum, expectedText) {
  const data = new Uint8Array(fs.readFileSync(filePath));
  const loadingTask = pdfjs.getDocument({ data });
  const pdf = await loadingTask.promise;
  
  console.log(`PDF loaded: ${filePath}`);
  console.log(`Total pages: ${pdf.numPages}`);
  
  if (pageNum > pdf.numPages || pageNum < 1) {
    console.log(`Page ${pageNum} is out of range.`);
    return;
  }
  
  const page = await pdf.getPage(pageNum);
  const textContent = await page.getTextContent();
  const strings = textContent.items.map(item => item.str).join(' ');
  
  console.log(`--- Text from Page ${pageNum} ---`);
  
  if (strings.toLowerCase().includes(expectedText.toLowerCase())) {
    console.log(`SUCCESS: Found expected text on page ${pageNum}`);
  } else {
    console.log(`FAILURE: Expected text NOT found on page ${pageNum}`);
    console.log(`Actual text contains: ${strings.substring(0, 1000)}...`);
    
    // Check neighboring pages just in case of off-by-one
    for (let p = Math.max(1, pageNum - 1); p <= Math.min(pdf.numPages, pageNum + 1); p++) {
        if (p === pageNum) continue;
        const adjPage = await pdf.getPage(p);
        const adjText = (await adjPage.getTextContent()).items.map(i => i.str).join(' ');
        if (adjText.toLowerCase().includes(expectedText.toLowerCase())) {
            console.log(`NOTE: Found text on page ${p} instead! (Off-by-one detected)`);
        }
    }
  }
}

const pdfPath = '/Users/tvishakhanna/Developer/Trace-Lit/backend/data/uploads/6c579906-58bd-473d-9d48-2e85cea918c9/llm1.pdf';
const pageNum = 2;
const textToFind = 'Chronological display of LLM releases';

verifyPdf(pdfPath, pageNum, textToFind).catch(console.error);
