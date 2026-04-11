# Context Package
> Built by ContextAssembler | 2026-04-11T11-58-37 | task: sprint-2: mike-product-calc 选品组合器 + 产品多选数量填写 + 实时毛利/利润/原料需求输出；基于现有 sprint-1 骨架继续开发；技术栈：pandas + streamlit + scipy + numpy；产出：完整功能代码 + 可运行验证
> Profile: standard | Target: subagent | Sections: [git, active, features, relevant] +conditional[features,contracts]

() => {
    const out = [];
    out.push(`## 📋 Git State  \[required\]`);
    out.push(`- **Branch**: \`${gitState.branch}\``);
    out.push(`- **Status**: ${gitState.status === '_clean_' ? '✅ clean' : '⚠️ dirty'}`);
    if (gitState.status !== '_clean_') {
      out.push(`\`\`\``);
      out.push(gitState.status);
      out.push(`\`\`\``);
    }
    out.push('');
    if (gitState.log) {
      out.push(`### 📜 Recent Commits (last ${limits.maxLogEntries})  \[required\]`);
      out.push('```');
      out.push(gitState.log);
      out.push('```');
      out.push('');
    }
    if (gitState.diff) {
      out.push(`### 🔍 Uncommitted Changes  \[conditional\]`);
      out.push('```');
      out.push(gitState.diff);
      out.push('```');
      out.push('');
    }
    return out.join('\n');
  }
() => {
    if (!activeState.hasActive) return null;
    const out = [];
    out.push(`## ⚡ Active Run  \[required\]`);
    out.push(`- **Type**: ${activeState.activeType}`);
    out.push(`- **Started**: ${activeState.startedAt}`);
    out.push(`- **Branch**: \`${activeState.branch}\``);
    if (activeState.brief) {
      out.push('');
      out.push(activeState.brief);
    }
    out.push('');
    return out.join('\n');
  }
() => {
    if (!featuresState) return null;
    const out = [];
    out.push(`## 🎯 Features (${featuresState.passing}/${featuresState.total} passing)  \[conditional\]`);
    if (featuresState.unfinished.length > 0) {
      out.push('### Unfinished:');
      for (const f of featuresState.unfinished) {
        const extras = [`priority=${f.priority}`, `size=${f.size || 'n/a'}`, `acceptance=${f.acceptanceCriteriaCount || 0}`].join(' | ');
        out.push(`- [ ] **${f.id}: ${f.title}** (${extras})`);
      }
    } else {
      out.push('✅ All features passing');
    }
    out.push('');
    return out.join('\n');
  }
() => {
    if (!contractsState) return null;
    const out = [];
    out.push(`## 📄 Latest Sprint Contract  \[conditional\]`);
    out.push(`**File**: \`${contractsState.latestFile}\``);
    out.push('');
    out.push(contractsState.summary);
    out.push('');
    return out.join('\n');
  }
---
*ContextAssembler v1 | 2026-04-11T11-58-37*