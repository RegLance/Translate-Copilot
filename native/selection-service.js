/**
 * Selection Service - 文本选择监控服务
 * 
 * 功能：监听全局文本选择事件，通过 stdout 输出 JSON 格式的选择信息
 * 输出格式：{"text": "选中的文本", "x": 100, "y": 200, "program": "程序名"}
 * 
 * 使用方式：node selection-service.js
 */

const SelectionHook = require('selection-hook');

// 创建选择钩子实例
const selectionHook = new SelectionHook();

// 防抖控制
let lastText = '';
let lastTime = 0;
const DEBOUNCE_MS = 100;

// 监听文本选择事件
selectionHook.on('text-selection', (data) => {
    const now = Date.now();
    
    // 防抖：相同文本在短时间内不重复输出
    if (data.text === lastText && now - lastTime < DEBOUNCE_MS) {
        return;
    }
    
    lastText = data.text;
    lastTime = now;
    
    // 输出 JSON 到 stdout
    const result = {
        text: data.text || '',
        x: data.selectionX || 0,
        y: data.selectionY || 0,
        program: data.programName || '',
        timestamp: now
    };
    
    console.log(JSON.stringify(result));
});

// 监听错误
selectionHook.on('error', (err) => {
    console.error(JSON.stringify({ error: err.message }));
});

// 启动监控
try {
    selectionHook.start();
    // 输出就绪信号
    console.log(JSON.stringify({ ready: true }));
} catch (err) {
    console.error(JSON.stringify({ error: err.message }));
    process.exit(1);
}

// 优雅退出
process.on('SIGINT', () => {
    selectionHook.stop();
    selectionHook.cleanup();
    process.exit(0);
});

process.on('SIGTERM', () => {
    selectionHook.stop();
    selectionHook.cleanup();
    process.exit(0);
});