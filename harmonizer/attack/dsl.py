"""Bounded, typed attack-rule parser and interpreter; never executes Python."""
from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations
import json
import math
import re
from lark import Lark
from lark.exceptions import LarkError
from .score import Degree, Figure, Interval, Key, Note, Pitch, Score, Voice, interval, pitch_of

class DSLError(ValueError):
  pass

GRAMMAR = r"""
?start: disjunction
?disjunction: conjunction ("or"i conjunction)* -> disjunction
?conjunction: negation ("and"i negation)* -> conjunction
?negation: "not"i negation -> logical_not
         | comparison
?comparison: sum
           | sum COMP sum -> compare
           | sum "is"i DIRECTION sum -> relation
?sum: product (ADD product)* -> arithmetic
?product: unary (MUL unary)* -> arithmetic
?unary: "-" unary -> negative
      | postfix
?postfix: atom ("." NAME)* -> attributes
?atom: NUMBER -> number
     | STRING -> string
     | PITCH -> pitch
     | INTERVAL -> interval_literal
     | DEGREE -> degree_literal
     | VOICE "attacks"i "at"i postfix -> attacks
     | VOICE "at"i postfix -> at
     | VOICE "before"i postfix -> before
     | VOICE -> voice
     | NAME "(" [disjunction ("," disjunction)*] ")" -> call
     | NAME -> variable
     | "(" disjunction ")"
COMP: "==" | "!=" | "<=" | ">=" | "<" | ">"
ADD: "+" | "-"
MUL: "*" | "/"
DIRECTION: "above"i | "below"i
PITCH.3: /[A-G][#b]*-?[0-9]+/
INTERVAL.3: /[PMmd][1-9][0-9]*/
DEGREE.3: /(?:b+|#+)[1-7](?![a-zA-Z0-9_])/
VOICE.2: /[SATB](?![a-zA-Z0-9_])/
NUMBER: /[0-9]+(?:\.[0-9]+)?/
NAME: /[a-zA-Z][a-zA-Z0-9_]*/
STRING: /"(?:[^"\\]|\\.)*"/
%import common.WS
%ignore WS
"""
PARSER = Lark(GRAMMAR, parser="lalr", maybe_placeholders=False)
NUMERIC = (int, float)
PITCH_TYPES = (Note, Pitch)

def literal(tree):
  text = str(tree.children[0])
  match tree.data:
    case "number":
      value = float(text) if "." in text else int(text)
      if not math.isfinite(value):
        raise DSLError("Numeric literals must be finite")
      return value
    case "string":
      return json.loads(text)
    case "pitch":
      return Pitch.parse(text)
    case "interval_literal":
      return Interval.parse(text)
    case "degree_literal":
      return Degree(int(text[-1]), text.count("#") - text.count("b"))
    case "voice":
      return Voice[text]
  raise DSLError("Not a literal")

def property_type(kind, name):
  allowed = {
    Note: {"previous": Note, "voice": Voice},
    Key: {"tonic": Pitch, "mode": str},
    Interval: {"steps": int, "semitones": int},
  }
  if name not in allowed.get(kind, {}):
    raise DSLError(f"Unsupported property {name!r} on {kind.__name__}")
  return allowed[kind][name]

def infer(tree, scope):
  c = tree.children
  match tree.data:
    case "number" | "string" | "pitch" | "interval_literal" | "degree_literal" | "voice":
      return type(literal(tree))
    case "variable":
      name = str(c[0])
      if name not in scope:
        raise DSLError(f"Unknown name {name!r}")
      return scope[name]
    case "attributes":
      kind = infer(c[0], scope)
      for name in c[1:]:
        kind = property_type(kind, str(name))
      return kind
    case "at" | "before" | "attacks":
      if infer(c[1], scope) not in (Note, Figure):
        raise DSLError("A time anchor must be a note or figure")
      return bool if tree.data == "attacks" else Note
    case "call":
      name, kinds = str(c[0]), [infer(x, scope) for x in c[1:]]
      if name in ("distance", "interval") and len(kinds) == 2 and all(k in PITCH_TYPES for k in kinds):
        return int if name == "distance" else Interval
      if name == "degree" and len(kinds) == 1 and kinds[0] in PITCH_TYPES:
        return Degree
      raise DSLError(f"Unsupported function or arguments: {name}")
    case "negative":
      kind = infer(c[0], scope)
      if kind not in (*NUMERIC, Interval):
        raise DSLError("Unary minus requires a number or interval")
      return kind
    case "arithmetic":
      kinds = [infer(x, scope) for x in c[::2]]
      if len(kinds) == 1:
        return kinds[0]
      if any(k not in NUMERIC for k in kinds):
        raise DSLError("Arithmetic requires numbers")
      return float
    case "logical_not":
      if infer(c[0], scope) is not bool:
        raise DSLError("not requires a condition")
      return bool
    case "conjunction" | "disjunction":
      kinds = [infer(x, scope) for x in c]
      if len(kinds) == 1:
        return kinds[0]
      if any(k is not bool for k in kinds):
        raise DSLError("and/or require conditions")
      return bool
    case "relation":
      a, b = infer(c[0], scope), infer(c[2], scope)
      if not ((a in PITCH_TYPES and b in PITCH_TYPES) or a is b is Voice):
        raise DSLError("above/below compares pitches or voice identities")
      return bool
    case "compare":
      a, b, op = infer(c[0], scope), infer(c[2], scope), str(c[1])
      valid = a in NUMERIC and b in NUMERIC
      if op in ("==", "!="):
        valid |= a is b and a in (str, Voice, Interval, Degree, Pitch)
        valid |= (a is Degree and b is int) or (b is Degree and a is int)
      if not valid:
        raise DSLError(f"Invalid comparison between {a.__name__} and {b.__name__}")
      return bool
  raise DSLError(f"Unsupported expression: {tree.data}")

def expression(text, scope):
  try:
    tree = PARSER.parse(text)
    if sum(1 for _ in tree.iter_subtrees()) > 200:
      raise DSLError("Expression is too large")
    return tree, infer(tree, scope)
  except (LarkError, ValueError, RecursionError) as error:
    raise DSLError(f"Invalid expression {text!r}: {error}") from error

@dataclass(frozen=True)
class Statement:
  kind: str
  expression: object
  line: int
  text: str
  name: str = ""
  body: tuple = ()

@dataclass(frozen=True)
class Trigger:
  kind: str
  names: tuple[str, ...]
  voice: Voice | tuple[Voice, ...] | None = None

  def bindings(self, score, time):
    attacks = sorted((n for n in score.notes if n.onset == time), key=lambda n: n.voice.value)
    match self.kind:
      case "single":
        selected = self.voice if isinstance(self.voice, tuple) else (self.voice,)
        values = [(n,) for n in attacks if self.voice is None or n.voice in selected]
      case "pair":
        values = combinations(attacks, 2)
      case "hold":
        held = sorted((n for n in score.notes if n.onset < time < n.offset), key=lambda n: n.voice.value)
        values = ((n, h) for n in attacks for h in held if n.voice != h.voice)
      case "figure":
        values = [(f,) for f in score.figures if f.onset == time]
    return [dict(zip(self.names, row)) for row in values]

@dataclass(frozen=True)
class Rule:
  id: str
  title: str
  trigger: Trigger
  body: tuple[Statement, ...]

def trigger(text):
  patterns = [
    (r"At attack \((\w+),\s*(\w+)\):", "pair"),
    (r"At attack (\w+) while (\w+) holds:", "hold"),
    (r"At ((?:soprano|alto|tenor|bass)(?: or (?:soprano|alto|tenor|bass))*) attack (\w+):", "single_voice"),
    (r"At attack (\w+):", "single"),
    (r"At figure (\w+):", "figure"),
  ]
  for pattern, kind in patterns:
    found = re.fullmatch(pattern, text, re.I)
    if found:
      names, voice = found.groups(), None
      if kind == "single_voice":
        voices = [Voice[v[0].upper()] for v in re.split(r" or ", names[0], flags=re.I)]
        if len(set(voices)) != len(voices):
          raise DSLError("Each voice may occur only once in a trigger")
        voice = voices[0] if len(voices) == 1 else tuple(sorted(voices, key=lambda v: v.value))
        names, kind = names[1:], "single"
      if len(set(names)) != len(names) or any(n in ("key", "S", "A", "T", "B") for n in names):
        raise DSLError("Trigger bindings must have distinct, non-reserved names")
      if any(not re.fullmatch(r"[a-z][a-zA-Z0-9_]*", n) for n in names):
        raise DSLError("Binding names must begin with a lowercase letter")
      return Trigger(kind, names, voice)
  raise DSLError(f"Invalid trigger: {text}")

def logical_lines(source):
  if len(source) > 100_000:
    raise DSLError("Rule source exceeds 100 KB")
  result, pending = [], None
  for number, raw in enumerate(source.splitlines(), 1):
    if "\t" in raw:
      raise DSLError(f"Line {number}: use spaces, not tabs")
    text = raw.strip()
    if not text or text.startswith("//"):
      continue
    indent = len(raw) - len(raw.lstrip())
    if indent % 2:
      raise DSLError(f"Line {number}: indentation must use multiples of two spaces")
    if pending:
      pending[2] += " " + text
      if text.endswith(":"):
        result.append(tuple(pending))
        pending = None
    elif text.lower().startswith("if ") and not text.endswith(":"):
      pending = [number, indent, text]
    else:
      result.append((number, indent, text))
  if pending:
    raise DSLError("Unterminated multiline if condition")
  return result

def parse(source):
  lines, rules, index = logical_lines(source), [], 0

  def body(start, indent, scope, depth=0):
    if depth > 12:
      raise DSLError("Blocks are nested too deeply")
    statements, scope = [], dict(scope)
    while start < len(lines) and lines[start][1] >= indent:
      line, actual, text = lines[start]
      if actual != indent:
        raise DSLError(f"Line {line}: unexpected indentation")
      if text.lower().startswith("let "):
        found = re.fullmatch(r"let ([a-z][a-zA-Z0-9_]*) = (.+)", text, re.I)
        if not found:
          raise DSLError(f"Line {line}: invalid let")
        name, value = found.groups()
        if name in scope:
          raise DSLError(f"Line {line}: name {name!r} is already bound")
        expr, kind = expression(value, scope)
        scope[name] = kind
        statements.append(Statement("let", expr, line, value, name))
        start += 1
      elif text.lower().startswith("if ") and text.endswith(":"):
        value = text[3:-1].strip()
        expr, kind = expression(value, scope)
        if kind is not bool:
          raise DSLError(f"Line {line}: if requires a Boolean condition")
        if start + 1 >= len(lines) or lines[start + 1][1] <= indent:
          raise DSLError(f"Line {line}: empty if block")
        nested, start = body(start + 1, lines[start + 1][1], scope, depth + 1)
        statements.append(Statement("if", expr, line, value, body=nested))
      elif text.lower().startswith("penalty "):
        value = text[8:].strip()
        expr, kind = expression(value, scope)
        if kind not in NUMERIC:
          raise DSLError(f"Line {line}: penalty requires a number")
        statements.append(Statement("penalty", expr, line, value))
        start += 1
      else:
        raise DSLError(f"Line {line}: unsupported statement {text!r}")
    return tuple(statements), start

  while index < len(lines):
    line, indent, text = lines[index]
    if indent:
      raise DSLError(f"Line {line}: triggers must start at column 1")
    selected = trigger(text)
    index += 1
    count = 0
    while index < len(lines) and lines[index][1] > 0:
      line, indent, text = lines[index]
      found = re.fullmatch(r'Rule ("(?:[^"\\]|\\.)*"):', text, re.I)
      if indent != 2 or not found:
        raise DSLError(f"Line {line}: expected a named Rule indented two spaces")
      title = json.loads(found[1])
      if index + 1 >= len(lines) or lines[index + 1][1] <= indent:
        raise DSLError(f"Line {line}: empty rule")
      scope = {n: Figure if selected.kind == "figure" else Note for n in selected.names}
      scope["key"] = Key
      first = index + 1
      statements, index = body(first, lines[first][1], scope)
      canonical = str(selected) + "\n" + "\n".join(f"{i}:{s}" for _, i, s in lines[first:index])
      identity = sha256(canonical.encode()).hexdigest()[:16]
      rules.append(Rule(identity, title, selected, statements))
      count += 1
    if not count:
      raise DSLError("Trigger section contains no rules")
  if not rules:
    raise DSLError("Rulebook is empty")
  if len({r.id for r in rules}) != len(rules):
    raise DSLError("Duplicate rule bodies would duplicate a feature")
  if len(rules) > 100:
    raise DSLError("Prototype rulebooks are limited to 100 rules")
  return tuple(rules)

@dataclass(frozen=True)
class Missing:
  reason: str

def evaluate_expression(tree, env, score):
  c = tree.children
  match tree.data:
    case "number" | "string" | "pitch" | "interval_literal" | "degree_literal" | "voice":
      return literal(tree)
    case "variable":
      return env[str(c[0])]
    case "attributes":
      value = evaluate_expression(c[0], env, score)
      for name in c[1:]:
        if isinstance(value, Missing):
          return value
        name = str(name)
        property_type(type(value), name)
        value = score.previous(value) if name == "previous" else getattr(value, name)
        if value is None:
          return Missing("No contiguous previous note (boundary or rest)")
      return value
    case "at" | "before" | "attacks":
      anchor = evaluate_expression(c[1], env, score)
      if isinstance(anchor, Missing):
        return anchor
      voice = Voice[str(c[0])]
      if tree.data == "attacks":
        return any(n.voice == voice and n.onset == anchor.onset for n in score.notes)
      return score.at(voice, anchor.onset, tree.data == "before") or Missing(f"{voice.name} is silent")
    case "call":
      values = [evaluate_expression(x, env, score) for x in c[1:]]
      missing = next((v for v in values if isinstance(v, Missing)), None)
      if missing:
        return missing
      match str(c[0]):
        case "distance":
          return abs(interval(*values).semitones)
        case "interval":
          return interval(*values)
        case "degree":
          return score.key.degree(pitch_of(values[0]))
    case "negative" | "logical_not":
      value = evaluate_expression(c[0], env, score)
      if isinstance(value, Missing):
        return value
      return -value if tree.data == "negative" else not value
    case "conjunction" | "disjunction":
      if len(c) == 1:
        return evaluate_expression(c[0], env, score)
      missing = None
      for child in c:
        value = evaluate_expression(child, env, score)
        if isinstance(value, Missing):
          missing = value
        elif tree.data == "conjunction" and value is False:
          return False
        elif tree.data == "disjunction" and value is True:
          return True
      return missing or (tree.data == "conjunction")
    case "arithmetic":
      value = evaluate_expression(c[0], env, score)
      for op, other in zip(c[1::2], c[2::2]):
        right = evaluate_expression(other, env, score)
        if isinstance(value, Missing) or isinstance(right, Missing):
          return value if isinstance(value, Missing) else right
        match str(op):
          case "+":
            value += right
          case "-":
            value -= right
          case "*":
            value *= right
          case "/":
            if right == 0:
              raise DSLError("Division by zero")
            value /= right
        if not math.isfinite(value):
          raise DSLError("Nonfinite arithmetic")
      return value
    case "compare" | "relation":
      a, b = evaluate_expression(c[0], env, score), evaluate_expression(c[2], env, score)
      if isinstance(a, Missing) or isinstance(b, Missing):
        return a if isinstance(a, Missing) else b
      op = str(c[1]).lower()
      if tree.data == "relation":
        if isinstance(a, Voice):
          a, b = -a.value, -b.value
        else:
          a, b = pitch_of(a).semitones, pitch_of(b).semitones
        return a > b if op == "above" else a < b
      if isinstance(a, Degree) and type(b) is int:
        b = Degree(b) if 1 <= b <= 7 else None
      elif isinstance(b, Degree) and type(a) is int:
        a = Degree(a) if 1 <= a <= 7 else None
      match op:
        case "==":
          return a == b
        case "!=":
          return a != b
        case "<":
          return a < b
        case "<=":
          return a <= b
        case ">":
          return a > b
        case ">=":
          return a >= b
  raise DSLError(f"Unsupported expression: {tree.data}")

@dataclass
class Evaluation:
  totals: dict[str, float]
  trace: list[dict]

def evaluate(rules, score: Score, start=None, stop=None, trace=True):
  totals, records = {r.id: 0.0 for r in rules}, []

  def run(statements, env, rule, time, binding):
    env = dict(env)
    for statement in statements:
      try:
        value = evaluate_expression(statement.expression, env, score)
      except (ArithmeticError, ValueError, TypeError) as error:
        raise DSLError(f"Rule {rule.title!r}, line {statement.line}, time {time}: {error}") from error
      if statement.kind == "let":
        env[statement.name] = value
        continue
      skipped = isinstance(value, Missing)
      if statement.kind == "if" and not skipped:
        if value:
          run(statement.body, env, rule, time, binding)
        continue
      if not skipped:
        if not math.isfinite(value):
          raise DSLError("Nonfinite penalty")
        totals[rule.id] += value
        if not math.isfinite(totals[rule.id]):
          raise DSLError("Nonfinite accumulated penalty")
      if trace:
        records.append({
          "rule_id": rule.id, "rule": rule.title, "time": str(time),
          "bindings": {name: item.id for name, item in binding.items()},
          "line": statement.line, "expression": statement.text,
          "status": "skipped" if skipped else "contribution",
          "reason": value.reason if skipped else None,
          "value": None if skipped else value,
        })

  for time in score.times:
    if (start is not None and time < start) or (stop is not None and time >= stop):
      continue
    for rule in rules:
      for binding in rule.trigger.bindings(score, time):
        run(rule.body, {**binding, "key": score.key}, rule, time, binding)
  return Evaluation(totals, records)
