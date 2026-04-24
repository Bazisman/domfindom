import { useMemo, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createCategory,
  deleteCategory,
  getCategories,
  updateCategory,
  type Category,
  type CategoryType,
} from "../lib/api";
import { categoryTypeLabel } from "../lib/labels";

const CATEGORY_TYPE_OPTIONS: Array<{ value: CategoryType; label: string }> = [
  { value: "expense", label: "Расход" },
  { value: "income", label: "Доход" },
  { value: "both", label: "Оба типа" },
];

const COLOR_PRESETS = [
  "#5f6b76",
  "#1d8f61",
  "#c15445",
  "#3578e5",
  "#c7762d",
  "#9b51e0",
  "#0ea5a8",
  "#d63384",
];

function getInitialFormState() {
  return {
    name: "",
    type: "expense" as CategoryType,
    color: COLOR_PRESETS[0],
  };
}

export function CategoriesPage() {
  const queryClient = useQueryClient();
  const [selectedType, setSelectedType] = useState<CategoryType | "all">("all");
  const [editingCategoryId, setEditingCategoryId] = useState<number | null>(null);
  const [formState, setFormState] = useState(getInitialFormState);
  const [formError, setFormError] = useState<string | null>(null);
  const formPanelRef = useRef<HTMLElement | null>(null);
  const nameInputRef = useRef<HTMLInputElement | null>(null);

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: getCategories,
  });

  const visibleCategories = useMemo(() => {
    const items = categories.data ?? [];
    if (selectedType === "all") {
      return items;
    }
    return items.filter((item) => item.type === selectedType || item.type === "both");
  }, [categories.data, selectedType]);

  const createMutation = useMutation({
    mutationFn: createCategory,
    onSuccess: async () => {
      resetForm();
      await queryClient.invalidateQueries({ queryKey: ["categories"] });
    },
    onError: (error: Error) => {
      setFormError(error.message);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      categoryId,
      payload,
    }: {
      categoryId: number;
      payload: Parameters<typeof updateCategory>[1];
    }) => updateCategory(categoryId, payload),
    onSuccess: async () => {
      resetForm();
      await queryClient.invalidateQueries({ queryKey: ["categories"] });
    },
    onError: (error: Error) => {
      setFormError(error.message);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCategory,
    onSuccess: async (_, categoryId) => {
      if (editingCategoryId === categoryId) {
        resetForm();
      }
      await queryClient.invalidateQueries({ queryKey: ["categories"] });
    },
    onError: (error: Error) => {
      setFormError(error.message);
    },
  });

  function resetForm() {
    setEditingCategoryId(null);
    setFormState(getInitialFormState());
    setFormError(null);
  }

  function moveToEditForm() {
    requestAnimationFrame(() => {
      formPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      window.setTimeout(() => {
        nameInputRef.current?.focus();
        nameInputRef.current?.select();
      }, 180);
    });
  }

  function fillFormFromCategory(category: Category) {
    setEditingCategoryId(category.id);
    setFormState({
      name: category.name,
      type: category.type,
      color: category.color,
    });
    setFormError(null);
    moveToEditForm();
  }

  function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const name = formState.name.trim();
    if (!name) {
      setFormError("Укажи название категории.");
      return;
    }

    const payload = {
      name,
      type: formState.type,
      color: formState.color,
    };

    if (editingCategoryId !== null) {
      updateMutation.mutate({ categoryId: editingCategoryId, payload });
      return;
    }

    createMutation.mutate(payload);
  }

  return (
    <main className="categories-layout">
      <section
        className={editingCategoryId !== null ? "panel panel-form editing-panel" : "panel panel-form"}
        ref={formPanelRef}
      >
        <div className="panel-header">
          <h2>{editingCategoryId ? "Редактирование категории" : "Новая категория"}</h2>
          <span>{editingCategoryId ? "Изменение" : "Создание"}</span>
        </div>

        <form className="transaction-form" onSubmit={submitForm}>
          {editingCategoryId !== null && (
            <div className="editing-banner" role="status">
              <strong>Сейчас редактируется:</strong> {formState.name || "категория"}
            </div>
          )}
          <label className="field">
            <span>Название</span>
            <input
              ref={nameInputRef}
              onChange={(event) =>
                setFormState((current) => ({ ...current, name: event.target.value }))
              }
              placeholder="Например, Продукты"
              value={formState.name}
            />
          </label>

          <label className="field">
            <span>Тип</span>
            <select
              onChange={(event) =>
                setFormState((current) => ({
                  ...current,
                  type: event.target.value as CategoryType,
                }))
              }
              value={formState.type}
            >
              {CATEGORY_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <div className="field">
            <span>Цвет</span>
            <div className="color-grid">
              {COLOR_PRESETS.map((color) => (
                <button
                  aria-label={`Выбрать цвет ${color}`}
                  className={formState.color === color ? "color-swatch active" : "color-swatch"}
                  key={color}
                  onClick={() => setFormState((current) => ({ ...current, color }))}
                  style={{ backgroundColor: color }}
                  type="button"
                />
              ))}
            </div>
          </div>

          {formError && <p className="form-error">{formError}</p>}

          <div className="action-row">
            <button
              className="primary-button"
              disabled={createMutation.isPending || updateMutation.isPending}
              type="submit"
            >
              {editingCategoryId
                ? updateMutation.isPending
                  ? "Сохраняем..."
                  : "Сохранить изменения"
                : createMutation.isPending
                  ? "Создаём..."
                  : "Добавить категорию"}
            </button>

            {editingCategoryId !== null && (
              <button className="ghost-button" onClick={resetForm} type="button">
                Отмена
              </button>
            )}
          </div>
        </form>
      </section>

      <section className="panel panel-list">
        <div className="panel-header">
          <h2>Категории</h2>
        </div>

        <div className="topbar-links category-filter-row">
          <button
            className={selectedType === "all" ? "toggle active" : "toggle"}
            onClick={() => setSelectedType("all")}
            type="button"
          >
            Все
          </button>
          {CATEGORY_TYPE_OPTIONS.map((option) => (
            <button
              className={selectedType === option.value ? "toggle active" : "toggle"}
              key={option.value}
              onClick={() => setSelectedType(option.value)}
              type="button"
            >
              {option.label}
            </button>
          ))}
        </div>

        <div className="category-card-grid">
          {visibleCategories.map((category) => (
            <article className="category-card" key={category.id}>
              <div className="category-card-main">
                <span
                  aria-hidden="true"
                  className="category-dot"
                  style={{ backgroundColor: category.color }}
                />
                <div>
                  <strong>{category.name}</strong>
                  <p>{categoryTypeLabel(category.type)}</p>
                </div>
              </div>
              <div className="category-card-actions">
                <button
                  className="ghost-button"
                  onClick={() => fillFormFromCategory(category)}
                  type="button"
                >
                  Изменить
                </button>
                <button
                  className="ghost-button"
                  disabled={deleteMutation.isPending}
                  onClick={() => deleteMutation.mutate(category.id)}
                  type="button"
                >
                  Отключить
                </button>
              </div>
            </article>
          ))}

          {!visibleCategories.length && (
            <p className="empty">
              {categories.isLoading
                ? "Загружаем категории..."
                : "Категорий для этого фильтра пока нет."}
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
