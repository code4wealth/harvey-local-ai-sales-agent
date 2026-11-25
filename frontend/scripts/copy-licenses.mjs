import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(frontendRoot, "..");
const nodeModules = resolve(frontendRoot, "node_modules");
const outputDir = resolve(frontendRoot, "static", "licenses");

const notices = [
  {
    name: "Harvey Local AI Sales Agent",
    path: resolve(repositoryRoot, "LICENSE"),
    file: "harvey-agpl-3.0.txt",
  },
  {
    name: "Sellbird / Harvey attribution notice",
    path: resolve(repositoryRoot, "NOTICE"),
    file: "harvey-notice.txt",
  },
  { name: "React", path: resolve(nodeModules, "react", "LICENSE"), file: "react-mit.txt" },
  { name: "React DOM", path: resolve(nodeModules, "react-dom", "LICENSE"), file: "react-dom-mit.txt" },
  { name: "Lucide React", path: resolve(nodeModules, "lucide-react", "LICENSE"), file: "lucide-react-isc.txt" },
  { name: "Tailwind CSS", path: resolve(nodeModules, "tailwindcss", "LICENSE"), file: "tailwindcss-mit.txt" },
  {
    name: "Inter Variable font",
    path: resolve(nodeModules, "@fontsource-variable", "inter", "LICENSE"),
    file: "inter-ofl-1.1.txt",
  },
  {
    name: "JetBrains Mono Variable font",
    path: resolve(nodeModules, "@fontsource-variable", "jetbrains-mono", "LICENSE"),
    file: "jetbrains-mono-ofl-1.1.txt",
  },
];

mkdirSync(outputDir, { recursive: true });
const sections = [];
for (const notice of notices) {
  const text = readFileSync(notice.path, "utf8");
  copyFileSync(notice.path, resolve(outputDir, notice.file));
  sections.push(`\n${"=".repeat(78)}\n${notice.name}\n${"=".repeat(78)}\n\n${text.trim()}\n`);
}
writeFileSync(
  resolve(outputDir, "THIRD_PARTY_NOTICES.txt"),
  `Sellbird AI dashboard bundle — third-party notices\n${sections.join("\n")}`,
  "utf8",
);
console.log(`Copied ${notices.length} licence notices to ${outputDir}`);
