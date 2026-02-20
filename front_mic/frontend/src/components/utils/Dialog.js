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

const NOTIFICATION_PLACEMENT = "bottomLeft";
const NOTIFICATION_DURATION = 2;

const tip = (msg) => {
  notification.open({
    message: msg,
    duration: NOTIFICATION_DURATION,
    placement: NOTIFICATION_PLACEMENT,
  });
};

const toastSuccess = (msg) => {
  notification.success({
    message: msg,
    duration: NOTIFICATION_DURATION,
    placement: NOTIFICATION_PLACEMENT,
  });
};

const toastWarning = (msg) => {
  notification.warning({
    message: msg,
    duration: NOTIFICATION_DURATION,
    placement: NOTIFICATION_PLACEMENT,
  });
};

const toastError = (msg) => {
  notification.error({
    message: msg,
    duration: NOTIFICATION_DURATION,
    placement: NOTIFICATION_PLACEMENT,
  });
};

export { showErr, showSuccess, showMsg, tip, toastSuccess, toastWarning, toastError };
