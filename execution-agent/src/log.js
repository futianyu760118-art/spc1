/** 关键事件 JSON 行日志（契约 §6：stdout 采集审计，warn/error 走 stderr） */
function emit(stream, level, event, fields) {
  stream.write(JSON.stringify({ ts: new Date().toISOString(), level, event, ...fields }) + '\n');
}

export function createLogger(level = 'info') {
  const debugEnabled = level === 'debug';
  return {
    debug: (event, fields = {}) => {
      if (debugEnabled) emit(process.stdout, 'debug', event, fields);
    },
    info: (event, fields = {}) => emit(process.stdout, 'info', event, fields),
    warn: (event, fields = {}) => emit(process.stderr, 'warn', event, fields),
    error: (event, fields = {}) => emit(process.stderr, 'error', event, fields),
  };
}
