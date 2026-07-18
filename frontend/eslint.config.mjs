// ESLint flat config (H3a). Scope: TS/TSX sources. The rules that matter
// most here are react-hooks — exhaustive-deps violations are real bugs in
// a polling/socket-heavy UI. Any disable must now point at a running rule.
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";

export default tseslint.config(
  {
    ignores: ["node_modules/**", ".next/**", "next-env.d.ts", "coverage/**"],
  },
  ...tseslint.configs.recommended,
  {
    files: ["**/*.ts", "**/*.tsx"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      // The two classic hooks rules as hard errors — exhaustive-deps
      // violations are real bugs in a polling/socket-heavy UI. The v7
      // compiler-era rules (refs-in-render, set-state-in-effect) flag
      // working latest-ref patterns here; adopt them in a dedicated pass.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "error",
      // Unused function args prefixed with _ are intentional (destructure-drop).
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
);
