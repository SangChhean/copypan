<?php
// 记录错误日志（如果可用）
ini_set('log_errors', 1);
ini_set('error_log', __DIR__ . '/php-error.log');

// 强制返回 200 状态码，防止 `418 I'm a teapot`
http_response_code(200);

// 启用错误显示（调试用，生产环境请移除）
error_reporting(E_ALL);
ini_set('display_errors', 1);

// 设置 JSON 响应头
header('Content-Type: application/json');
header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Methods: GET, OPTIONS");
header("Access-Control-Allow-Headers: Content-Type");

// **DreamHost 共享主机不支持 SetEnv，因此我们从 URL 读取 API 地址**
$apiGatewayUrl = $_GET['api_url'] ?? "https://default-api-url.com";

// 确保 API Gateway URL 不是空的
if (!$apiGatewayUrl || $apiGatewayUrl === "https://default-api-url.com") {
    http_response_code(500);
    echo json_encode(["error" => "API_GATEWAY_URL 未配置或未正确读取"]);
    exit;
}

// 输出调试信息
echo json_encode(["status" => "ok", "api_url" => $apiGatewayUrl]);
exit;
?>
