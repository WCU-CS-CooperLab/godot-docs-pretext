extends "res://addons/gdpractice/tester/test.gd"


func _build_checks() -> void:
	var practice_slot = _practice

	var c1 := Check.new()
	c1.description = "Run graphical program"
	c1.checker = func() -> String:
		return ""
	
	

	checks.append_array([c1])
