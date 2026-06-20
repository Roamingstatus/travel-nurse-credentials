import assert from "node:assert/strict";
import test from "node:test";

import {
  CredantaAIError,
  MAX_RESUME_INPUT_CHARS,
  createOpenAIService,
  isOpenAIConfigured,
  validateOpenAIConfiguration,
} from "./openaiService.ts";

function createLogger() {
  return {
    entries: [] as Array<{ level: "info" | "error"; args: unknown[] }>,
    info(...args: unknown[]) {
      this.entries.push({ level: "info", args });
    },
    error(...args: unknown[]) {
      this.entries.push({ level: "error", args });
    },
  };
}

test("service initializes correctly with an injected client", async () => {
  const client = {
    responses: {
      async create() {
        return {
          output_text: JSON.stringify({
            professionalVersion: "Professional",
            recruiterVersion: "Recruiter",
            impactVersion: "Impact",
            suggestedKeywords: ["ICU", "patient care"],
            improvementNotes: ["Use stronger action verbs."],
          }),
        };
      },
    },
  };

  const service = createOpenAIService({ client, logger: createLogger() });
  const result = await service.generateResumeVersions({
    resumeText: "Managed ICU patient care.",
  });

  assert.equal(result.professionalVersion, "Professional");
});

test("missing API key is handled cleanly", async () => {
  const service = createOpenAIService({ env: {}, logger: createLogger() });

  await assert.rejects(
    () => service.generateResumeVersions({ resumeText: "Clinical resume." }),
    (error) =>
      error instanceof CredantaAIError &&
      error.code === "OPENAI_API_KEY_MISSING" &&
      error.statusCode === 503,
  );
});

test("empty resume is rejected", async () => {
  const service = createOpenAIService({
    env: { OPENAI_API_KEY: "test-key" },
    logger: createLogger(),
  });

  await assert.rejects(
    () => service.generateResumeVersions({ resumeText: "   " }),
    (error) =>
      error instanceof CredantaAIError &&
      error.code === "RESUME_TEXT_REQUIRED" &&
      error.statusCode === 400,
  );
});

test("oversized resume is rejected", async () => {
  const service = createOpenAIService({
    env: { OPENAI_API_KEY: "test-key" },
    logger: createLogger(),
  });

  await assert.rejects(
    () =>
      service.generateResumeVersions({
        resumeText: "x".repeat(MAX_RESUME_INPUT_CHARS + 1),
      }),
    (error) =>
      error instanceof CredantaAIError &&
      error.code === "RESUME_TEXT_TOO_LARGE" &&
      error.statusCode === 413,
  );
});

test("valid response is parsed correctly", async () => {
  const service = createOpenAIService({
    logger: createLogger(),
    client: {
      responses: {
        async create() {
          return {
            output_text: JSON.stringify({
              professionalVersion: "Refined professional version",
              recruiterVersion: "Recruiter-facing version",
              impactVersion: "Impact-driven version",
              suggestedKeywords: ["travel nursing", "credentialing"],
              improvementNotes: ["Quantify outcomes already present in the resume."],
            }),
          };
        },
      },
    },
  });

  const result = await service.generateResumeVersions({
    resumeText: "Supported credentialing for travel nursing assignments.",
    targetRole: "Travel Nurse",
  });

  assert.deepEqual(result.suggestedKeywords, ["travel nursing", "credentialing"]);
  assert.equal(result.impactVersion, "Impact-driven version");
});

test("OpenAI failure is handled gracefully", async () => {
  const logger = createLogger();
  const service = createOpenAIService({
    logger,
    client: {
      responses: {
        async create() {
          throw new Error("raw provider failure with internal details");
        },
      },
    },
  });

  await assert.rejects(
    () => service.generateResumeVersions({ resumeText: "Clinical resume." }),
    (error) =>
      error instanceof CredantaAIError &&
      error.code === "OPENAI_OPERATION_FAILED" &&
      error.statusCode === 502 &&
      !error.message.includes("internal details"),
  );

  assert.equal(logger.entries.at(-1)?.level, "error");
});

test("isOpenAIConfigured reports key presence without exposing it", () => {
  assert.equal(isOpenAIConfigured({ OPENAI_API_KEY: "test-key" }), true);
  assert.equal(isOpenAIConfigured({ OPENAI_API_KEY: "   " }), false);
  assert.equal(isOpenAIConfigured({}), false);
});

test("startup validation warns in development when key is missing", () => {
  const warnings: unknown[][] = [];
  validateOpenAIConfiguration(
    { NODE_ENV: "development" },
    { warn: (...args: unknown[]) => warnings.push(args) },
  );

  assert.equal(warnings.length, 1);
  assert.match(String(warnings[0][0]), /OPENAI_API_KEY is missing/);
});

test("startup validation fails in production when key is missing", () => {
  assert.throws(
    () => validateOpenAIConfiguration({ NODE_ENV: "production" }),
    (error) =>
      error instanceof CredantaAIError &&
      error.code === "OPENAI_API_KEY_MISSING" &&
      error.message === "OPENAI_API_KEY is missing",
  );
});

test("startup validation succeeds when key exists", () => {
  assert.doesNotThrow(() =>
    validateOpenAIConfiguration({ NODE_ENV: "production", OPENAI_API_KEY: "test-key" }),
  );
});
