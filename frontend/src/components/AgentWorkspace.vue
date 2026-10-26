<template>
  <div class="agent-layout">
    <div class="panel"><slot name="conversation" /></div>
    <div class="panel">
      <div class="panel-head"><h3>示例问题</h3></div>
      <slot name="examples" />
      <div class="table-wrap"><slot name="followup" /></div>
    </div>
  </div>
</template>
