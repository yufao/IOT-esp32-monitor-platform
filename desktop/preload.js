// 预加载脚本：用于将安全 API 暴露给渲染层

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("slsApi", {
	openSdManager: () => ipcRenderer.invoke("ui:openSdManager"),

	sendCommand: (args) => ipcRenderer.invoke("server:sendCommand", args),
	getCommandStatus: (args) => ipcRenderer.invoke("server:getCommandStatus", args),
});
