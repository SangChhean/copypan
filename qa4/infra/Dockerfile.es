# qa4-es 镜像：elasticsearch 8.19.0 + 从本机 elasticsearch8 复制的 analysis-ik 插件
# 词典配置目录不打进镜像，运行时只读挂载 ./ik_config
FROM elasticsearch:8.19.0

USER root

# 源容器 plugins/analysis-ik：uid=0 gid=0，文件 mode=755
COPY ik_plugin/analysis-ik /usr/share/elasticsearch/plugins/analysis-ik
RUN chown -R 0:0 /usr/share/elasticsearch/plugins/analysis-ik \
    && find /usr/share/elasticsearch/plugins/analysis-ik -type f -exec chmod 755 {} \; \
    && find /usr/share/elasticsearch/plugins/analysis-ik -type d -exec chmod 755 {} \;

USER elasticsearch
