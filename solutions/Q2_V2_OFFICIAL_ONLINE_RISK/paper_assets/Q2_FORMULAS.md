# Q2 ONLINE 公式

## 候选评分

$$Score^A_{c,d}=C^{realized}_{c,d}$$

$$Score^B_{c,d}=C^{realized}_{c,d}+\lambda(E^*-E_{c,d,end})$$

## 在线选择

$$c^*(d)=\arg\min_c\frac{1}{|W_d|}\sum_{j\in W_d}Score_{c,j}$$

其中 $W_d\subset\{1,\ldots,d-1\}$，窗口长度为 28 天。

## 信息边界

$$\max scenario\_date_{d,s}<d$$

所有候选共享同一预测、场景基础池、初始真实 SOC、执行器、电池参数和结算规则。

## Initial SOC

$$E_{Jan1,0}=6000\text{ kWh}$$

题目没有单独规定2月1日初始SOC。本文使用

$$E_{Feb1,0}=6000\text{ kWh}$$

作为中性初始化假设，并报告1200、3000、6000、9000、10800 kWh的敏感性。

## Unutilized surplus

$$W_t=G_t+V_t+D_t-L_t-C_t$$

代码中的`spill`表示未利用剩余供给量，不解释为严格的PV curtailment。
