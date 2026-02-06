import { defineStore } from "pinia";

export const useStore = defineStore("store", {
  state: () => ({
    selectedIndex: ["0"],
    showIndex: false,
    role: "",
    username: "",
    showInfo: 1,
    showMsgs: [],
    showMsgOpen: false,
    hilights: [],
    refid: "",
    openMsg: false,
  }),
});
