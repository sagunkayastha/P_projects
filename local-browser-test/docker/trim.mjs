// stdio MCP filter: runs the given MCP server command and cuts long tool-result text so a whole-page
// snapshot cannot overflow the chat model's context (the llama.cpp chat page sends tool output uncut).
// Usage: node trim.mjs <server command...>   (TRIM_CHARS, default 16000; chat-mcp-up.sh sets 5000)
import { spawn } from 'node:child_process';
import readline from 'node:readline';
const MAX = +(process.env.TRIM_CHARS || 16000);
const [cmd, ...args] = process.argv.slice(2);
const child = spawn(cmd, args, { stdio: ['pipe', 'pipe', 'inherit'] });
process.stdin.pipe(child.stdin);
readline.createInterface({ input: child.stdout }).on('line', (line) => {
  try {
    const msg = JSON.parse(line);
    for (const c of msg?.result?.content ?? []) {
      if (c.type === 'text' && c.text.length > MAX) {
        c.text = c.text.slice(0, MAX) + `\n[output cut: showed ${MAX} of ${c.text.length} characters. ` +
          `To read a specific part, use evaluate_script that returns only that text (e.g. one element's innerText).]`;
      }
    }
    process.stdout.write(JSON.stringify(msg) + '\n');
  } catch { process.stdout.write(line + '\n'); }
});
child.on('exit', (code) => process.exit(code ?? 0));
