#include <stdio.h>
#define MaxSize 100

typedef int DataType;

typedef struct {
    DataType data[MaxSize];
    int length;
} SeqList;

/*
 * 参数：L 为顺序表指针；a 为待存入的数据数组；n 为元素个数。
 * 功能：将数组 a 的前 n 个元素依次存入顺序表 L，并设置表长。
 * 返回：成功返回 1；若 n 超过 MaxSize，返回 0，并输出"顺序表的空间不够，无法建立顺序表\n"。
 */
int CreatList(SeqList *L, DataType a[], int n) {
    //=====begin=====
    if(n > MaxSize){
        printf("顺序表的空间不够，无法建立顺序表\n"); 
        return 0;
    } 
    for(int i = 0; i < n; i++) L->data[i] = a[i];
    L->length = n;
    return 1;
    
    //======end======
}

/*
 * 参数：L 为顺序表指针。
 * 功能：依次输出顺序表 L 中所有数据元素，元素之间以空格分隔。
 */
void PrintList(SeqList *L) {
    //=====begin=====
    for(int i = 0; i < L->length; i++) printf("%d ",L->data[i]);
    printf("\n");
    
    //======end======
}

/*
 * 参数：L 为顺序表指针；x 为待查找的元素值。
 * 功能：在顺序表 L 中按值查找元素 x，找到则返回其逻辑序号。
 * 返回：找到返回序号（从 1 开始）；未找到返回 0。
 */
int Locate(SeqList *L, DataType x) {
    //=====begin=====
    for(int i = 0; i < L->length; i++){
        if(L->data[i] == x) return i+1;
    }
    return 0;
    
    //======end======
}
/*
 * 参数：L 为顺序表指针；i 为插入位置（逻辑序号）；x 为待插入元素。
 * 功能：在顺序表 L 的第 i 个位置插入元素 x，表长加 1。
 * 返回：插入成功返回 1；上溢或位置错误返回 0，并分别输出"上溢错误，插入失败\n"或者"位置错误，插入失败\n"。
 */
int Insert(SeqList *L, int i, DataType x) {
    //=====begin=====
    if(L->length >= MaxSize){
        printf("上溢错误，插入失败\n");
        return 0;
    } 
    if(i < 1 || i > L->length + 1){
        printf("位置错误，插入失败\n");
        return 0;
    }
    for(int j = L->length; j >= i; j--){
        L->data[j] = L->data[j-1];
    }
    L->data[i-1] = x;
    L->length++;
    return 1;
    
    //======end======
}
/*
 * 参数：L 为顺序表指针；i 为删除位置（逻辑序号）；ptr 用于带回被删元素。
 * 功能：删除顺序表 L 的第 i 个元素，并用 ptr 保存被删除的值。
 * 返回：删除成功返回 1；下溢或位置错误返回 0，并分别输出"下溢错误，删除失败\n"或者"位置错误，删除失败\n"。
 */
int Delete(SeqList *L, int i, DataType *ptr) {
    //=====begin=====
    if(L->length == 0){
        printf("下溢错误，删除失败\n");
        return 0;
    }
    if(i<1 || i > L->length){
        printf("位置错误，删除失败\n");
        return 0;
    }
    *ptr = L->data[i-1];
    for(int j = i; j < L->length; j++) L->data[j-1] = L->data[j];
    L->length--;
    return 1;
    //======end======
}

/*
 * 参数：L 为顺序表指针。
 * 功能：获取顺序表 L 当前的长度。
 * 返回：返回顺序表当前元素个数。
 */
int Length(SeqList *L) {
    //=====begin=====
    return L->length;
    //======end======
}

int main() {
    int r[5] = {1, 2, 3, 4, 5};
    int i, x;
    SeqList L;

    /* 建立顺序表 */
    CreatList(&L, r, 5);
    printf("顺序表元素：");
    PrintList(&L);

    /* 输出长度 */
    printf("顺序表长度为：%d\n", Length(&L));

    /* 按值查找 */
    // 请输入要查找的元素
    scanf("%d", &x);
    i = Locate(&L, x);
    if (i != 0) {
        printf("元素 %d 的位置是：%d\n", x, i);
    } else {
        printf("元素 %d 不存在\n", x);
    }

    /* 插入操作 */
    // 输入插入位置和插入元素
    scanf("%d%d", &i, &x);
    if (Insert(&L, i, x)) {
        printf("插入后顺序表：");
        PrintList(&L);
    }

    /* 删除操作 */
    // 输入删除位置
    scanf("%d", &i);
    if (Delete(&L, i, &x)) {
        printf("删除的元素是：%d\n", x);
        printf("删除后顺序表：");
        PrintList(&L);
    }

    return 0;
}