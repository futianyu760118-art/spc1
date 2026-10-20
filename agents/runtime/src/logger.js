"use strict";

const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };

function createLogger(getLevel) {
  return function log(level, event, fields = {}) {
    if (LEVELS[level] < LEVELS[getLevel()]) return;
    const line = JSON.stringify({ ts: new Date().toISOString(), level, event, ...fields });
    if (level === "error") console.error(line);
    else console.log(line);
  };
}

module.exports = { createLogger };
