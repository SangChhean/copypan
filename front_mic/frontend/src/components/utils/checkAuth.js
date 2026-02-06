import axios from "axios";
import { storeToRefs } from "pinia";
import { useStore } from "../../store/index";

const { showIndex, role, username } = storeToRefs(useStore());

const jumpToLogin = () => {
  window.location.hash = "/login";
};

const checkSession = (u = "") => {
  let token = localStorage.getItem("token") || null;
  if (!token) jumpToLogin();
  axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  axios
    .get("/api/testToken")
    .then((res) => {
      if (res.data.status == "OK") {
        showIndex.value = true;
        role.value = res.data.userinfo.role;
        username.value = res.data.userinfo.username;

        if (u) {
          if (role.value != u) window.location.hash = "pg403";
        }
      } else jumpToLogin();
    })
    .catch((err) => {
      console.log(err);
      jumpToLogin();
    });
};

export default checkSession;
