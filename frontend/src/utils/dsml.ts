const DSML_BLOCK_RE = /<[｜|]+DSML[｜|]+\s*(?:tool_)?calls\b[^>]*>[\s\S]*?<\/[｜|]+DSML[｜|]+\s*(?:tool_)?calls\s*>/gi
const DSML_TAG_RE = /<\/?[｜|]+DSML[｜|]+\s*[^>]*>/gi
const TOOL_CALL_BLOCK_RE = /<tool_call\b[^>]*>[\s\S]*?<\/tool_call\s*>/gi
const TOOL_CALL_TAG_RE = /<\/?tool_call\b[^>]*>/gi

export function stripDsmlMarkup(content: string): string {
  return content
    .replace(DSML_BLOCK_RE, '')
    .replace(DSML_TAG_RE, '')
    .replace(TOOL_CALL_BLOCK_RE, '')
    .replace(TOOL_CALL_TAG_RE, '')
    .trim()
}
