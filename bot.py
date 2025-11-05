class ConstructionBot:
    def __init__(self):
        self.objects = {}
        self.confirmations = ['да', 'yes', 'y', 'д']

    def request_confirmation(self, action):
        response = input(f"Подтвердите {action} (да/нет): ").lower()
        return response in self.confirmations

    def add_object(self):
        name = input("Введите название объекта: ")
        if not self.request_confirmation("добавление объекта"):
            print("Отменено")
            return
        self.objects[name] = {'salaries': [], 'materials': []}
        print(f"Объект '{name}' добавлен")

    def add_salary(self):
        obj = self.select_object()
        if not obj: return
        
        amount = input("Введите сумму зарплаты: ")
        if not self.request_confirmation("добавление зарплаты"):
            print("Отменено")
            return
        self.objects[obj]['salaries'].append(float(amount))
        print("Зарплата добавлена")

    def add_material(self):
        obj = self.select_object()
        if not obj: return
        
        name = input("Введите название материала: ")
        cost = input("Введите стоимость материала: ")
        if not self.request_confirmation("добавление материала"):
            print("Отменено")
            return
        self.objects[obj]['materials'].append({
            'name': name,
            'cost': float(cost)
        })
        print("Материал добавлен")

    def edit_object(self):
        old_name = self.select_object()
        if not old_name: return
        
        new_name = input("Введите новое название: ")
        if not self.request_confirmation("изменение объекта"):
            print("Отменено")
            return
        self.objects[new_name] = self.objects.pop(old_name)
        print("Объект изменен")

    def delete_object(self):
        name = self.select_object()
        if not name: return
        
        if not self.request_confirmation("удаление объекта"):
            print("Отменено")
            return
        del self.objects[name]
        print("Объект удален")

    def select_object(self):
        if not self.objects:
            print("Нет добавленных объектов")
            return None
            
        print("Список объектов:")
        for i, name in enumerate(self.objects.keys(), 1):
            print(f"{i}. {name}")
        
        try:
            num = int(input("Выберите номер объекта: "))
            return list(self.objects.keys())[num-1]
        except (ValueError, IndexError):
            print("Неверный номер")
            return None

    def show_data(self):
        if not self.objects:
            print("Данные отсутствуют")
            return
            
        for obj_name, data in self.objects.items():
            print(f"\nОбъект: {obj_name}")
            print("Зарплаты:", data['salaries'])
            print("Материалы:")
            for material in data['materials']:
                print(f"  {material['name']}: {material['cost']} руб.")

    def run(self):
        actions = {
            '1': self.add_object,
            '2': self.add_salary,
            '3': self.add_material,
            '4': self.edit_object,
            '5': self.delete_object,
            '6': self.show_data
        }
        
        while True:
            print("\n1. Добавить объект")
            print("2. Добавить зарплату")
            print("3. Добавить материал")
            print("4. Редактировать объект")
            print("5. Удалить объект")
            print("6. Показать данные")
            print("0. Выход")
            
            choice = input("Выберите действие: ")
            
            if choice == '0':
                break
            if choice in actions:
                actions[choice]()
            else:
                print("Неверный ввод")

if __name__ == "__main__":
    bot = ConstructionBot()
    bot.run()
