import customtkinter as ctk

# Настройки внешнего вида
ctk.set_appearance_mode("dark")      # "dark", "light", "system"
ctk.set_default_color_theme("blue")  # "blue", "green", "dark-blue"


class Calculator(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Калькулятор")
        self.geometry("360x520")
        self.resizable(False, False)

        # Цвета
        self.bg_color = "#1e1e2e"
        self.display_bg = "#2a2a3c"
        self.btn_num = "#3a3a4e"
        self.btn_num_hover = "#4a4a5e"
        self.btn_op = "#ff9500"
        self.btn_op_hover = "#ffad33"
        self.btn_func = "#505068"
        self.btn_func_hover = "#606078"
        self.btn_eq = "#4caf50"
        self.btn_eq_hover = "#66bb6a"

        self.configure(fg_color=self.bg_color)

        # Переменные
        self.expression = ""
        self.result_var = ctk.StringVar(value="0")
        self.history_var = ctk.StringVar(value="")

        # Дисплей
        self._build_display()

        # Кнопки
        self._build_buttons()

        # Привязка клавиатуры
        self.bind("<Key>", self._on_key)

    def _build_display(self):
        display_frame = ctk.CTkFrame(
            self, fg_color=self.display_bg, corner_radius=20, height=130
        )
        display_frame.pack(fill="x", padx=20, pady=(20, 10))
        display_frame.pack_propagate(False)

        # История (мелкий текст сверху)
        history_label = ctk.CTkLabel(
            display_frame,
            textvariable=self.history_var,
            font=("Segoe UI", 16),
            text_color="#8888a0",
            anchor="e",
        )
        history_label.pack(fill="x", padx=20, pady=(15, 0))

        # Основной результат
        result_label = ctk.CTkLabel(
            display_frame,
            textvariable=self.result_var,
            font=("Segoe UI", 42, "bold"),
            text_color="#ffffff",
            anchor="e",
        )
        result_label.pack(fill="x", padx=20, pady=(5, 15))

    def _build_buttons(self):
        buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        buttons_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Сетка 4x5
        for i in range(4):
            buttons_frame.grid_columnconfigure(i, weight=1, uniform="btn")
        for i in range(5):
            buttons_frame.grid_rowconfigure(i, weight=1, uniform="btn")

        # (текст, строка, столбец, тип, colspan)
        layout = [
            ("C",  0, 0, "func", 1),
            ("±",  0, 1, "func", 1),
            ("%",  0, 2, "func", 1),
            ("÷",  0, 3, "op",   1),
            ("7",  1, 0, "num",  1),
            ("8",  1, 1, "num",  1),
            ("9",  1, 2, "num",  1),
            ("×",  1, 3, "op",   1),
            ("4",  2, 0, "num",  1),
            ("5",  2, 1, "num",  1),
            ("6",  2, 2, "num",  1),
            ("−",  2, 3, "op",   1),
            ("1",  3, 0, "num",  1),
            ("2",  3, 1, "num",  1),
            ("3",  3, 2, "num",  1),
            ("+",  3, 3, "op",   1),
            ("0",  4, 0, "num",  2),  # растянутая кнопка
            (".",  4, 2, "num",  1),
            ("=",  4, 3, "eq",   1),
        ]

        for text, row, col, kind, colspan in layout:
            self._make_button(buttons_frame, text, row, col, kind, colspan)

    def _make_button(self, parent, text, row, col, kind, colspan):
        colors = {
            "num":  (self.btn_num, self.btn_num_hover, "#ffffff"),
            "op":   (self.btn_op, self.btn_op_hover, "#ffffff"),
            "func": (self.btn_func, self.btn_func_hover, "#ffffff"),
            "eq":   (self.btn_eq, self.btn_eq_hover, "#ffffff"),
        }
        fg, hover, text_color = colors[kind]

        btn = ctk.CTkButton(
            parent,
            text=text,
            font=("Segoe UI", 22, "bold"),
            fg_color=fg,
            hover_color=hover,
            text_color=text_color,
            corner_radius=18,
            command=lambda: self._on_button(text),
        )
        btn.grid(
            row=row, column=col, columnspan=colspan,
            padx=5, pady=5, sticky="nsew"
        )

    # --- Логика ---
    def _on_button(self, value):
        if value == "C":
            self.expression = ""
            self.result_var.set("0")
            self.history_var.set("")
        elif value == "=":
            self._calculate()
        elif value == "±":
            self._toggle_sign()
        elif value == "%":
            self._percent()
        else:
            self._append(value)

    def _append(self, value):
        # Не даём вводить два оператора подряд
        operators = "+−×÷"
        if value in operators and self.expression and self.expression[-1] in operators:
            self.expression = self.expression[:-1] + value
        else:
            self.expression += value

        # Обновляем дисплей
        self.result_var.set(self.expression or "0")
        self.history_var.set("")

    def _calculate(self):
        if not self.expression:
            return
        # Заменяем символы на Python-операторы
        expr = (
            self.expression
            .replace("×", "*")
            .replace("÷", "/")
            .replace("−", "-")
        )
        try:
            # Безопасное вычисление
            result = eval(expr, {"__builtins__": {}}, {})
            # Форматирование: убираем .0 у целых
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            self.history_var.set(self.expression + " =")
            self.result_var.set(str(result))
            self.expression = str(result)
        except ZeroDivisionError:
            self.result_var.set("Деление на 0")
            self.expression = ""
        except Exception:
            self.result_var.set("Ошибка")
            self.expression = ""

    def _toggle_sign(self):
        if not self.expression:
            return
        try:
            expr = (
                self.expression.replace("×", "*")
                .replace("÷", "/").replace("−", "-")
            )
            result = eval(expr, {"__builtins__": {}}, {})
            self.expression = str(-result)
            self.result_var.set(self.expression)
        except Exception:
            pass

    def _percent(self):
        if not self.expression:
            return
        try:
            expr = (
                self.expression.replace("×", "*")
                .replace("÷", "/").replace("−", "-")
            )
            result = eval(expr, {"__builtins__": {}}, {}) / 100
            self.expression = str(result)
            self.result_var.set(self.expression)
        except Exception:
            pass

    def _on_key(self, event):
        key = event.char
        if key.isdigit() or key in ".+-*/":
            mapping = {"*": "×", "/": "÷", "-": "−", "+": "+"}
            self._append(mapping.get(key, key))
        elif event.keysym == "Return" or key == "=":
            self._calculate()
        elif event.keysym == "BackSpace":
            self.expression = self.expression[:-1]
            self.result_var.set(self.expression or "0")
        elif event.keysym == "Escape":
            self._on_button("C")


if __name__ == "__main__":
    app = Calculator()
    app.mainloop()