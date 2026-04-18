function isOperator(token: string) {
  return token === "+" || token === "-" || token === "*" || token === "/";
}

function precedence(token: string) {
  if (token === "+" || token === "-") {
    return 1;
  }
  if (token === "*" || token === "/") {
    return 2;
  }
  return 0;
}

function applyOperator(values: number[], operator: string) {
  if (values.length < 2) {
    return false;
  }

  const right = values.pop() as number;
  const left = values.pop() as number;

  if (operator === "+") {
    values.push(left + right);
    return true;
  }
  if (operator === "-") {
    values.push(left - right);
    return true;
  }
  if (operator === "*") {
    values.push(left * right);
    return true;
  }
  if (operator === "/") {
    if (right === 0) {
      return false;
    }
    values.push(left / right);
    return true;
  }

  return false;
}

export function evaluateAmountExpression(rawValue: string): number | null {
  const normalized = rawValue.replace(",", ".").replace(/\s+/g, "");
  if (!normalized) {
    return null;
  }
  if (!/^[\d.+\-*/()]+$/.test(normalized)) {
    return null;
  }

  const tokens = normalized.match(/\d+(?:\.\d+)?|[()+\-*/]/g);
  if (!tokens || tokens.join("") !== normalized) {
    return null;
  }

  const values: number[] = [];
  const operators: string[] = [];
  let previousToken = "";

  for (const token of tokens) {
    const isUnaryMinus = token === "-" && (!previousToken || previousToken === "(" || isOperator(previousToken));
    if (isUnaryMinus) {
      values.push(0);
    }

    if (/^\d/.test(token)) {
      const value = Number(token);
      if (Number.isNaN(value)) {
        return null;
      }
      values.push(value);
      previousToken = token;
      continue;
    }

    if (token === "(") {
      operators.push(token);
      previousToken = token;
      continue;
    }

    if (token === ")") {
      while (operators.length > 0 && operators[operators.length - 1] !== "(") {
        if (!applyOperator(values, operators.pop() as string)) {
          return null;
        }
      }
      if (operators.pop() !== "(") {
        return null;
      }
      previousToken = token;
      continue;
    }

    if (!isOperator(token)) {
      return null;
    }

    while (
      operators.length > 0 &&
      isOperator(operators[operators.length - 1]) &&
      precedence(operators[operators.length - 1]) >= precedence(token)
    ) {
      if (!applyOperator(values, operators.pop() as string)) {
        return null;
      }
    }

    operators.push(token);
    previousToken = token;
  }

  while (operators.length > 0) {
    const operator = operators.pop() as string;
    if (operator === "(" || operator === ")") {
      return null;
    }
    if (!applyOperator(values, operator)) {
      return null;
    }
  }

  if (values.length !== 1) {
    return null;
  }

  const result = values[0];
  if (!Number.isFinite(result)) {
    return null;
  }
  return result;
}
