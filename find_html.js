const fs = require('fs');

const transcriptPath = 'C:\\Users\\ayush\\.gemini\\antigravity\\brain\\513e55ea-5980-414c-ae23-dab46b1de433\\.system_generated\\logs\\transcript_full.jsonl';
const lines = fs.readFileSync(transcriptPath, 'utf8').split('\n');

for (const line of lines) {
  if (!line.trim()) continue;
  try {
    const obj = JSON.parse(line);
    if (obj.step_index === 156) {
       fs.writeFileSync('landing.html', obj.content);
       console.log('Saved landing.html (maybe)');
    }
    if (obj.step_index === 193) {
       fs.writeFileSync('dashboard.html', obj.content);
       console.log('Saved dashboard.html (maybe)');
    }
  } catch(e) {}
}
