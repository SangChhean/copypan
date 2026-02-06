import { Modal, message, notification } from "ant-design-vue";

const showErr = (msg) => {
  Modal.error({
    title: msg,
    okText: "确定",
  });
};

const showSuccess = (msg, hash = null) => {
  Modal.success({
    title: msg,
    okText: "确定",
    onOk() {
      if (hash) window.location.hash = hash;
    },
  });
};

const showMsg = (msg) => {
  message.info(msg, 2);
};

const tip = (msg) => {
  notification.open({
    message: msg,
    duration: 2,
    top: "120px",
  });
};

export { showErr, showSuccess, showMsg, tip };
