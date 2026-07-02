import tkinter as tk
from calc import add, subtract, multiply, divide

class CalculatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Calculator")
        
        self.current_input = ""
        self.result = None
        self.operator = None
        
        self.display = tk.Entry(root, width=40, borderwidth=5)
        self.display.grid(row=0, column=0, columnspan=4, padx=10, pady=10)
        
        # Clear button on Row 1 spanning 3 columns
        self.clear_button = tk.Button(root, text="C", width=32, height=3, command=self.clear_calculator)
        self.clear_button.grid(row=1, column=0, columnspan=3)
        
        # Division '/' button on Row 1, Column 3
        self.div_button = tk.Button(root, text="/", width=10, height=3, command=lambda: self.on_button_click("/"))
        self.div_button.grid(row=1, column=3)
        
        # Grid of other buttons
        buttons = [
            ('7', 2, 0), ('8', 2, 1), ('9', 2, 2), ('*', 2, 3),
            ('4', 3, 0), ('5', 3, 1), ('6', 3, 2), ('-', 3, 3),
            ('1', 4, 0), ('2', 4, 1), ('3', 4, 2), ('+', 4, 3),
            ('0', 5, 0), ('.', 5, 1)
        ]
        
        for (text, row, col) in buttons:
            button = tk.Button(root, text=text, width=10, height=3,
                               command=lambda t=text: self.on_button_click(t))
            button.grid(row=row, column=col)
            
        # Equal '=' button on Row 5, Column 2, spanning 2 columns
        self.equal_button = tk.Button(root, text="=", width=22, height=3, command=lambda: self.on_button_click("="))
        self.equal_button.grid(row=5, column=2, columnspan=2)
    
    def on_button_click(self, value):
        if value == '=':
            try:
                self.calculate_result()
            except ValueError as e:
                self.display.delete(0, tk.END)
                self.display.insert(0, str(e))
        elif value in ['+', '-', '*', '/']:
            self.set_operator(value)
        else:
            self.append_to_input(value)
    
    def append_to_input(self, value):
        if value == '.' and '.' in self.current_input:
            return
        self.current_input += value
        self.display.delete(0, tk.END)
        self.display.insert(0, self.current_input)
    
    def set_operator(self, operator):
        if self.operator is not None and self.current_input != "":
            try:
                self.calculate_result()
            except ValueError:
                # Abort setting new operator if intermediate calculation failed (e.g., division by zero)
                return
        
        if self.current_input != "":
            try:
                self.result = float(self.current_input)
            except ValueError:
                self.result = 0.0
            self.current_input = ""
        elif self.result is None:
            self.result = 0.0
            
        self.operator = operator
    
    def calculate_result(self):
        if self.operator is None or self.current_input == "":
            return
        
        second_operand = float(self.current_input)
        
        try:
            if self.operator == '+':
                self.result = add(self.result, second_operand)
            elif self.operator == '-':
                self.result = subtract(self.result, second_operand)
            elif self.operator == '*':
                self.result = multiply(self.result, second_operand)
            elif self.operator == '/':
                self.result = divide(self.result, second_operand)
            
            self.display.delete(0, tk.END)
            self.display.insert(0, str(self.result))
        except ValueError as e:
            self.display.delete(0, tk.END)
            self.display.insert(0, str(e))
        
        self.current_input = ""
        self.operator = None
        
    def clear_calculator(self):
        self.current_input = ""
        self.result = None
        self.operator = None
        self.display.delete(0, tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    app = CalculatorApp(root)
    root.mainloop()