const clients = new Set();

const send = (res, event) => {
  res.write(`data: ${JSON.stringify(event)}\n\n`);
};

const addClient = (res) => {
  clients.add(res);
  send(res, {
    type: "connected",
    data: {
      clientCount: clients.size,
    },
  });
};

const removeClient = (res) => {
  clients.delete(res);
};

const broadcast = (type, data) => {
  const event = {
    type,
    data,
    pushedAt: new Date().toISOString(),
  };

  for (const client of clients) {
    send(client, event);
  }

  return event;
};

module.exports = {
  addClient,
  removeClient,
  broadcast,
};
