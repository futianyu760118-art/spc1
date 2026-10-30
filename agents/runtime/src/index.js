"use strict";

const { startAgent, runAgent, safeCancel, createLocalRunHandler } = require("./bootstrap");
const { HubConnection } = require("./protocol");
const { startHealthServer, readJsonBody } = require("./health-server");
const { createConfig } = require("./config");
const { createRemoteConfig } = require("./remote-config");
const { createLogger } = require("./logger");
const { createHttpClient, UpstreamError, mapCode } = require("./http-client");
const {
  normalizeCaller,
  normalizeRequestId,
  normalizeTargetAgentRef,
  buildRunContext,
} = require("./run-context");
const { roundDurationMs, normalizeResult, splitOutcome } = require("./run-result");
const { ERROR_CODES, normalizeRunErrorCode } = require("./error-codes");
const { createAdapter: createOrderWriteAdapter } = require("./order-write-adapter");

module.exports = {
  createAgent: startAgent,
  startAgent,
  runAgent,
  safeCancel,
  createLocalRunHandler,
  HubConnection,
  normalizeCaller,
  normalizeRequestId,
  normalizeTargetAgentRef,
  buildRunContext,
  roundDurationMs,
  normalizeResult,
  splitOutcome,
  ERROR_CODES,
  normalizeRunErrorCode,
  createOrderWriteAdapter,
  startHealthServer,
  readJsonBody,
  createConfig,
  createRemoteConfig,
  createLogger,
  createHttpClient,
  UpstreamError,
  mapCode,
};
