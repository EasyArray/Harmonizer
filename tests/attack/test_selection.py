from harmonizer.attack.select_model import choose


def fixture():
  policy={"reference_model":"seed+melodic","minimum_improvement_nats":0.02,
          "minimum_piece_win_fraction":0.6,"simplicity_tolerance_nats":0.01}
  results={"summary":{"seed+melodic":{"mean_piece_nll":4},"base+proposal:simple":{"mean_piece_nll":3.905},
                      "base+all-proposals":{"mean_piece_nll":3.9}},
           "by_piece":{str(i):{"seed+melodic":4,"base+proposal:simple":3.905,"base+all-proposals":3.9} for i in range(5)}}
  return results,policy


def test_simplicity_preferred_in_near_tie():
  results,policy=fixture()
  assert choose(results,policy)=="base+proposal:simple"


def test_majority_and_minimum_gain_required():
  results,policy=fixture()
  for i in range(3):
    results["by_piece"][str(i)]["base+proposal:simple"]=5
    results["by_piece"][str(i)]["base+all-proposals"]=5
  assert choose(results,policy)=="seed+melodic"
  results,policy=fixture()
  results["summary"]["base+proposal:simple"]["mean_piece_nll"]=3.99
  results["summary"]["base+all-proposals"]["mean_piece_nll"]=3.99
  assert choose(results,policy)=="seed+melodic"
