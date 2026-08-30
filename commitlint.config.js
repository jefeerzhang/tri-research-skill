module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'type-enum': [2, 'always', [
      'feat', 'fix', 'docs', 'style', 'refactor',
      'perf', 'test', 'chore', 'ci', 'revert'
    ]],
    'type-case': [2, 'always', 'lower-case'],
    'type-empty': [2, 'never'],
    'subject-empty': [2, 'never'],
    'subject-max-length': [2, 'always', 100],
    // 允许中文字符，关闭 subject-case 限制
    'subject-case': [0],
    // 关闭 header-max-length 或放宽（中文占宽较大）
    'header-max-length': [2, 'always', 120],
    'body-max-line-length': [1, 'always', 200],
    'footer-max-line-length': [1, 'always', 200]
};
