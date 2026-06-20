import OpenAI from "openai";

export const DEFAULT_MODEL = process.env.OPENAI_MODEL || "gpt-5.4-mini";
export const MAX_RESUME_INPUT_CHARS = 20_000;
export const MAX_RESUME_OUTPUT_TOKENS = 1_800;

export interface GenerateResumeVersionsInput {
  resumeText: string;
  targetRole?: string;
  userId?: string;
}

export interface ResumeVersionsResult {
  professionalVersion: string;
  recruiterVersion: string;
  impactVersion: string;
  suggestedKeywords: string[];
  improvementNotes: string[];
}

export interface ChecklistSuggestionsInput {
  userId?: string;
}

export interface LayoutSuggestionsInput {
  userId?: string;
}

export interface AIUsageDecision {
  allowed: boolean;
  reason?: string;
}

export interface OpenAIClientLike {
  responses: {
    create: (params: Record<string, unknown>) => Promise<OpenAIResponseLike>;
  };
}

interface OpenAIResponseLike {
  output_text?: string;
  output?: unknown;
}

type ServiceEnv = Record<string, string | undefined>;

interface ServiceOptions {
  client?: OpenAIClientLike;
  env?: ServiceEnv;
  logger?: Pick<Console, "info" | "error">;
}

export class CredantaAIError extends Error {
  code: string;
  statusCode: number;
  publicMessage: string;

  constructor(publicMessage: string, code: string, statusCode = 500) {
    super(publicMessage);
    this.name = "CredantaAIError";
    this.code = code;
    this.statusCode = statusCode;
    this.publicMessage = publicMessage;
  }
}

const resumeVersionsSchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    professionalVersion: { type: "string" },
    recruiterVersion: { type: "string" },
    impactVersion: { type: "string" },
    suggestedKeywords: {
      type: "array",
      items: { type: "string" },
    },
    improvementNotes: {
      type: "array",
      items: { type: "string" },
    },
  },
  required: [
    "professionalVersion",
    "recruiterVersion",
    "impactVersion",
    "suggestedKeywords",
    "improvementNotes",
  ],
};

let cachedOpenAIClient: OpenAIClientLike | null = null;

export function isOpenAIConfigured(env: ServiceEnv = process.env): boolean {
  return Boolean((env.OPENAI_API_KEY || "").trim());
}

export function validateOpenAIConfiguration(
  env: ServiceEnv = process.env,
  logger: Pick<Console, "warn"> = console,
): void {
  if (isOpenAIConfigured(env)) {
    return;
  }

  if (env.NODE_ENV === "production") {
    throw new CredantaAIError(
      "OPENAI_API_KEY is missing",
      "OPENAI_API_KEY_MISSING",
      503,
    );
  }

  logger.warn("[openai] OPENAI_API_KEY is missing; AI features will be unavailable.");
}

function getConfiguredClient(env: ServiceEnv): OpenAIClientLike {
  const apiKey = (env.OPENAI_API_KEY || "").trim();

  if (!apiKey) {
    throw new CredantaAIError(
      "AI service is not configured. Please add OPENAI_API_KEY on the server.",
      "OPENAI_API_KEY_MISSING",
      503,
    );
  }

  if (!cachedOpenAIClient) {
    cachedOpenAIClient = new OpenAI({ apiKey });
  }

  return cachedOpenAIClient;
}

function logEvent(
  logger: Pick<Console, "info" | "error">,
  operation: string,
  model: string,
  success: boolean,
  error?: unknown,
): void {
  const basePayload = {
    timestamp: new Date().toISOString(),
    operation,
    model,
    success,
  };

  if (success) {
    logger.info("[openai]", basePayload);
    return;
  }

  logger.error("[openai]", {
    ...basePayload,
    error:
      error instanceof CredantaAIError
        ? { code: error.code, message: error.publicMessage }
        : { code: "OPENAI_OPERATION_FAILED", message: "OpenAI request failed" },
  });
}

function validateResumeInput(input: GenerateResumeVersionsInput): void {
  const resumeText = input.resumeText?.trim();

  if (!resumeText) {
    throw new CredantaAIError(
      "Please provide resume text before using AI resume suggestions.",
      "RESUME_TEXT_REQUIRED",
      400,
    );
  }

  if (resumeText.length > MAX_RESUME_INPUT_CHARS) {
    throw new CredantaAIError(
      `Resume text is too long for AI processing. Please keep it under ${MAX_RESUME_INPUT_CHARS.toLocaleString()} characters.`,
      "RESUME_TEXT_TOO_LARGE",
      413,
    );
  }
}

function buildResumePrompt(input: GenerateResumeVersionsInput): string {
  const targetRole = input.targetRole?.trim()
    ? `Target role: ${input.targetRole.trim()}`
    : "Target role: Healthcare role not specified";

  return [
    "You are helping Credanta users improve resume wording for healthcare recruiting.",
    targetRole,
    "",
    "Rules:",
    "- Do not invent experience.",
    "- Do not invent certifications.",
    "- Do not invent licenses.",
    "- Do not invent employers.",
    "- Preserve factual content.",
    "- Improve wording only.",
    "- If a detail is unclear or missing, do not add it.",
    "",
    "Return only structured JSON matching the provided schema.",
    "",
    "Resume text:",
    input.resumeText.trim(),
  ].join("\n");
}

function parseResumeVersions(response: OpenAIResponseLike): ResumeVersionsResult {
  const rawText =
    typeof response.output_text === "string"
      ? response.output_text
      : extractResponseText(response.output);

  if (!rawText) {
    throw new CredantaAIError(
      "AI response could not be read. Please try again.",
      "OPENAI_RESPONSE_EMPTY",
      502,
    );
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(rawText);
  } catch {
    throw new CredantaAIError(
      "AI response was not valid JSON. Please try again.",
      "OPENAI_RESPONSE_INVALID_JSON",
      502,
    );
  }

  if (!isResumeVersionsResult(parsed)) {
    throw new CredantaAIError(
      "AI response did not match the expected resume format. Please try again.",
      "OPENAI_RESPONSE_SCHEMA_MISMATCH",
      502,
    );
  }

  return parsed;
}

function extractResponseText(output: unknown): string {
  if (!Array.isArray(output)) {
    return "";
  }

  return output
    .flatMap((item) => {
      if (!item || typeof item !== "object" || !("content" in item)) {
        return [];
      }

      const content = (item as { content?: unknown }).content;
      if (!Array.isArray(content)) {
        return [];
      }

      return content
        .map((part) => {
          if (!part || typeof part !== "object" || !("text" in part)) {
            return "";
          }

          return typeof (part as { text?: unknown }).text === "string"
            ? (part as { text: string }).text
            : "";
        })
        .filter(Boolean);
    })
    .join("\n");
}

function isResumeVersionsResult(value: unknown): value is ResumeVersionsResult {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as ResumeVersionsResult;
  return (
    typeof candidate.professionalVersion === "string" &&
    typeof candidate.recruiterVersion === "string" &&
    typeof candidate.impactVersion === "string" &&
    Array.isArray(candidate.suggestedKeywords) &&
    candidate.suggestedKeywords.every((keyword) => typeof keyword === "string") &&
    Array.isArray(candidate.improvementNotes) &&
    candidate.improvementNotes.every((note) => typeof note === "string")
  );
}

function toPublicAIError(error: unknown): CredantaAIError {
  if (error instanceof CredantaAIError) {
    return error;
  }

  return new CredantaAIError(
    "AI suggestions are temporarily unavailable. Please try again shortly.",
    "OPENAI_OPERATION_FAILED",
    502,
  );
}

export function canUseAI(_userId?: string): AIUsageDecision {
  return { allowed: true };
}

export function trackAIUsage(_userId?: string): void {
  // Placeholder for future per-user usage accounting and rate limits.
}

export function createOpenAIService(options: ServiceOptions = {}) {
  const env = options.env || process.env;
  const logger = options.logger || console;

  function getClient(): OpenAIClientLike {
    return options.client || getConfiguredClient(env);
  }

  return {
    async generateResumeVersions(
      input: GenerateResumeVersionsInput,
      model = DEFAULT_MODEL,
    ): Promise<ResumeVersionsResult> {
      const operation = "generateResumeVersions";

      try {
        validateResumeInput(input);

        const usageDecision = canUseAI(input.userId);
        if (!usageDecision.allowed) {
          throw new CredantaAIError(
            usageDecision.reason || "AI usage is not available for this account.",
            "AI_USAGE_NOT_ALLOWED",
            429,
          );
        }

        const response = await getClient().responses.create({
          model,
          max_output_tokens: MAX_RESUME_OUTPUT_TOKENS,
          input: buildResumePrompt(input),
          text: {
            format: {
              type: "json_schema",
              name: "credanta_resume_versions",
              strict: true,
              schema: resumeVersionsSchema,
            },
          },
        });

        const parsed = parseResumeVersions(response);
        trackAIUsage(input.userId);
        logEvent(logger, operation, model, true);
        return parsed;
      } catch (error) {
        const publicError = toPublicAIError(error);
        logEvent(logger, operation, model, false, publicError);
        throw publicError;
      }
    },

    async generateChecklistSuggestions(
      _input: ChecklistSuggestionsInput = {},
      _model = DEFAULT_MODEL,
    ): Promise<never> {
      throw new CredantaAIError(
        "Smart Checklist AI suggestions are not implemented yet.",
        "AI_METHOD_NOT_IMPLEMENTED",
        501,
      );
    },

    async generateLayoutSuggestions(
      _input: LayoutSuggestionsInput = {},
      _model = DEFAULT_MODEL,
    ): Promise<never> {
      throw new CredantaAIError(
        "AI Layout Suggestions are not implemented yet.",
        "AI_METHOD_NOT_IMPLEMENTED",
        501,
      );
    },
  };
}

validateOpenAIConfiguration();

export const openAIService = createOpenAIService();
