import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: 5,
  duration: "20s",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{endpoint:incidents}": ["p(95)<1000"],
    "http_req_duration{endpoint:replay}": ["p(95)<3000"],
  },
};

const baseUrl = __ENV.BASE_URL || "http://localhost:3000";

export default function () {
  const incidents = http.get(`${baseUrl}/api/v1/incidents`, {
    tags: { endpoint: "incidents" },
  });
  check(incidents, { "incident list is healthy": (response) => response.status === 200 });

  const replay = http.get(`${baseUrl}/api/v1/demo/replays/deploy-timeout-showcase`, {
    tags: { endpoint: "replay" },
  });
  check(replay, {
    "cached replay is healthy": (response) =>
      response.status === 200 && response.json("ranked_hypotheses.0.score") >= 0.75,
  });
  sleep(0.2);
}
