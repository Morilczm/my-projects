const fs = require("fs");
const path = require("path");

const DEFAULT_STATE = {
  orders: [],
  feedbacks: [],
  messages: [],
  vehicle: {
    vehicleId: "CY-01",
    vehicleName: "雏雁一号",
    battery: 88,
    latency: 78,
    occupancy: 36,
    status: "idle",
    speed: 5,
    direction: "静止",
    eta: 8.7,
    updatedAt: new Date().toISOString(),
  },
};

const DATA_FILE = path.join(__dirname, "..", "data", "campuslife.json");

const clone = (value) => JSON.parse(JSON.stringify(value));

const ensureDataFile = () => {
  const dataDir = path.dirname(DATA_FILE);

  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }

  if (!fs.existsSync(DATA_FILE)) {
    fs.writeFileSync(DATA_FILE, JSON.stringify(DEFAULT_STATE, null, 2));
  }
};

const readState = () => {
  ensureDataFile();

  try {
    const raw = fs.readFileSync(DATA_FILE, "utf8");
    const parsed = JSON.parse(raw);
    return {
      ...clone(DEFAULT_STATE),
      ...parsed,
      vehicle: {
        ...clone(DEFAULT_STATE.vehicle),
        ...(parsed.vehicle || {}),
      },
    };
  } catch (err) {
    throw new Error(`数据文件读取失败: ${err.message}`);
  }
};

const writeState = (state) => {
  ensureDataFile();
  fs.writeFileSync(DATA_FILE, JSON.stringify(state, null, 2));
};

const updateState = (updater) => {
  const state = readState();
  const nextState = updater(state) || state;
  writeState(nextState);
  return nextState;
};

module.exports = {
  readState,
  updateState,
};
