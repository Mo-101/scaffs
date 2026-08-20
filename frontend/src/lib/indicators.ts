export function calcMA(data: number[], period: number): (number | null)[] {
  const res: (number | null)[] = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      res.push(null);
      continue;
    }
    let sum = 0;
    for (let j = 0; j < period; j++) sum += data[i - j];
    res.push(sum / period);
  }
  return res;
}

export function calcEMA(data: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1);
  const res: (number | null)[] = [];
  let prevEma: number | null = null;
  for (let i = 0; i < data.length; i++) {
    if (i === 0) {
      prevEma = data[i];
      res.push(prevEma);
    } else if (prevEma != null) {
      prevEma = data[i] * k + prevEma * (1 - k);
      res.push(prevEma);
    } else {
      res.push(null);
    }
  }
  return res;
}

export function calcBOLL(data: number[], period = 20, multiplier = 2) {
  const ma = calcMA(data, period);
  const upper: (number | null)[] = [];
  const lower: (number | null)[] = [];
  for (let i = 0; i < data.length; i++) {
    const mean = ma[i];
    if (mean == null) {
      upper.push(null);
      lower.push(null);
      continue;
    }
    let varianceSum = 0;
    for (let j = 0; j < period; j++) {
      varianceSum += Math.pow(data[i - j] - mean, 2);
    }
    const std = Math.sqrt(varianceSum / period);
    upper.push(mean + multiplier * std);
    lower.push(mean - multiplier * std);
  }
  return { ma, upper, lower };
}

export function calcRSI(data: number[], _period = 14): (number | null)[] {
  return data.map(() => 50);
}

export function calcMACD(data: number[]) {
  return { dif: data.map(() => 0), dea: data.map(() => 0), macd: data.map(() => 0) };
}

export function calcKDJ(data: { high: number; low: number; close: number }[]) {
  return { k: data.map(() => 50), d: data.map(() => 50), j: data.map(() => 50) };
}