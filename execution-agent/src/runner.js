import { spawn } from 'node:child_process';
import { CAPABILITY_NAME, PATH_WHITELIST } from './config.js';

const KILL_GRACE_MS = 2000;
const STDERR_TAIL_LIMIT = 500;

/** 单活动 run；忙时拒绝（设计 §3 边界决策）。recall/断线后杀子进程且不回报（契约 §5）。 */
export function createRunner(config, log) {
  let active = null;

  function fail(send, runId, code, message) {
    send({ type: 'run_failed', runId, error: { code, message } });
  }

  function cleanup(run) {
    clearTimeout(run.timeoutTimer);
    clearTimeout(run.killTimer);
    if (active === run) active = null;
  }

  function start(dispatch, send) {
    const { runId, capability, input } = dispatch ?? {};
    if (!runId) return;
    if (active) {
      fail(send, runId, 'INTERNAL_ERROR', 'agent busy');
      return;
    }
    if (capability !== CAPABILITY_NAME) {
      fail(send, runId, 'INVALID_ARGUMENT', `未知 capability: ${capability}`);
      return;
    }
    if (
      !input ||
      typeof input !== 'object' ||
      typeof input.path !== 'string' ||
      !PATH_WHITELIST.includes(input.path)
    ) {
      fail(send, runId, 'INVALID_ARGUMENT', 'path 不在白名单（契约 §4.2）');
      return;
    }
    const params = input.params ?? {};
    if (typeof params !== 'object' || params === null || Array.isArray(params)) {
      fail(send, runId, 'INVALID_ARGUMENT', 'params 必须是对象');
      return;
    }

    send({ type: 'run_update', runId, state: 'running' });
    log.info('run_started', { runId, path: input.path });

    let child;
    try {
      child = spawn(config.pythonBin, [config.queryScript, input.path, JSON.stringify(params)], {
        stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
      });
    } catch (err) {
      fail(send, runId, 'INTERNAL_ERROR', `无法启动查询子进程: ${err.message}`);
      return;
    }

    const run = {
      runId,
      child,
      recalled: false,
      settled: false,
      timedOut: false,
      stdoutText: '',
      stderrText: '',
      timeoutTimer: null,
      killTimer: null,
    };
    active = run;

    run.timeoutTimer = setTimeout(() => {
      run.timedOut = true;
      child.kill('SIGKILL');
    }, config.queryTimeoutMs);

    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk) => {
      run.stdoutText += chunk;
    });
    child.stderr.setEncoding('utf8');
    child.stderr.on('data', (chunk) => {
      run.stderrText += chunk;
    });

    child.on('error', (err) => {
      if (run.settled || run.recalled) return;
      run.settled = true;
      fail(send, runId, 'INTERNAL_ERROR', `查询子进程异常: ${err.message}`);
      cleanup(run);
    });

    child.on('close', () => {
      if (run.recalled) {
        log.info('run_recalled_done', { runId: run.runId });
        cleanup(run);
        return;
      }
      if (run.settled) {
        cleanup(run);
        return;
      }
      run.settled = true;
      const output = run.stdoutText.trim();
      let parsed = null;
      if (output) {
        try {
          parsed = JSON.parse(output);
        } catch {
          parsed = null;
        }
      }
      if (parsed && parsed.ok === true) {
        send({ type: 'run_complete', runId, result: parsed.data });
        log.info('run_complete', { runId });
      } else if (parsed && parsed.ok === false && parsed.error && typeof parsed.error.code === 'string') {
        send({ type: 'run_failed', runId, error: parsed.error });
        log.info('run_failed', { runId, code: parsed.error.code });
      } else if (run.timedOut) {
        send({
          type: 'run_failed',
          runId,
          error: { code: 'UPSTREAM_TIMEOUT', message: `查询超时（>${config.queryTimeoutMs}ms）` },
        });
        log.info('run_failed', { runId, code: 'UPSTREAM_TIMEOUT' });
      } else {
        const tail = run.stderrText.trim().slice(-STDERR_TAIL_LIMIT);
        send({
          type: 'run_failed',
          runId,
          error: {
            code: 'INTERNAL_ERROR',
            message: tail || `查询子进程异常退出（stdout 长度 ${output.length}）`,
          },
        });
        log.info('run_failed', { runId, code: 'INTERNAL_ERROR' });
      }
      cleanup(run);
    });
  }

  function killActive() {
    if (!active) return;
    const run = active;
    run.recalled = true;
    run.child.kill('SIGTERM');
    run.killTimer = setTimeout(() => {
      try {
        run.child.kill('SIGKILL');
      } catch {
        /* 进程已退出 */
      }
    }, KILL_GRACE_MS);
  }

  function recall(runId) {
    if (!active) {
      log.warn('recall_ignored_no_active_run', { runId: runId ?? null });
      return false;
    }
    if (runId && active.runId !== runId) {
      log.warn('recall_ignored_run_mismatch', { runId, currentRunId: active.runId });
      return false;
    }
    log.info('recalled', { runId: active.runId });
    killActive();
    return true;
  }

  function abortActive() {
    if (active) log.info('run_aborted', { runId: active.runId });
    killActive();
  }

  return {
    start,
    recall,
    abortActive,
    isBusy: () => active !== null,
    currentRunId: () => (active ? active.runId : null),
  };
}
